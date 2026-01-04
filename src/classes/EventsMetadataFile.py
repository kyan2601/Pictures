import os
import glob
import pandas as pd
from datetime import datetime
import shutil
from collections import defaultdict

from src import constants, helper
from src.classes.EventEntry import EventEntry
from src.classes.MetadataFile import MetadataFile


def _calculate_next_event_index(year, month):
    """
    Calculate the next event index for a given year and month.
    
    Event folders follow the pattern: [mm]_[event_num]_[month_name]_[title]
    This function finds the highest existing event_index for the given month.
    
    Edge cases handled:
    - Month is always 2-digit (01-12) from strftime('%m')
    - Malformed folder names are skipped (can't parse index)
    - No existing events returns 1
    """
    max_event_index = 0
    existing_events = glob.glob(os.path.join(constants.ROOT_DIR, str(year), str(month) + '_*'))

    for event_path in existing_events:
        if os.path.isdir(event_path):
            dir_name = os.path.basename(event_path)
            try:
                # Expected format: [mm]_[event_num]_[month_name]_[title]
                # Extract event_num from position [1] after splitting by '_'
                parts = dir_name.split('_', 2)
                if len(parts) >= 2:
                    index = int(parts[1])
                    max_event_index = max(max_event_index, index)
            except (ValueError, IndexError):
                # Skip malformed folder names (e.g., "01_abc_January_Event" where abc isn't a number)
                # This shouldn't happen if folder naming is correct, but handle gracefully
                continue

    return max_event_index + 1


class EventsMetadataFile:
    _instances = {}

    def __init__(self):
        if EventsMetadataFile._get_key() in EventsMetadataFile._instances.keys():
            raise RuntimeError("EventsMetadataFile is a singleton class, please call static method get_instance() instead")

        self.filepath = constants.EVENTS_FILEPATH
        self.df = None
        self.load()

    @staticmethod
    def _get_key():
        return "events"

    @staticmethod
    def get_instance():
        key = EventsMetadataFile._get_key()
        if key not in EventsMetadataFile._instances.keys():
            EventsMetadataFile._instances[key] = EventsMetadataFile()
        return EventsMetadataFile._instances[key]

    def load(self):
        if not os.path.exists(self.filepath):
            raise RuntimeError("ERROR: Events metadata file does not exist! Please investigate.")

        self.df = pd.read_csv(self.filepath)

    def write(self):
        if self.df is None:
            raise RuntimeError(f"Tried to write out events metadata file but dataframe is None")

        self.df = self.df[constants.EVENTS_COLS]
        self.df.to_csv(self.filepath, index=False)

    def _next_event_id(self):
        event_id = 1
        if len(self.df) > 0:
            event_id = self.df['event_id'].max() + 1
        return int(event_id)

    def create_event(self, title, start_date, end_date,
                     description=None, nominal_month=None) -> EventEntry:
        print(f'[*] Staging new event: {title}')
        start_date_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_dt = datetime.strptime(end_date, '%Y-%m-%d')

        # 1. VALIDATION AND PLANNING
        if start_date_dt > end_date_dt:
            raise RuntimeError(f"Invalid date range: start_date ({start_date}) must be <= end_date ({end_date})")

        if len(self.df) > 0:
            for _, existing_event in self.df.iterrows():
                existing_start = datetime.strptime(existing_event['start_date'], '%Y-%m-%d')
                existing_end = datetime.strptime(existing_event['end_date'], '%Y-%m-%d')
                if start_date_dt <= existing_end and existing_start <= end_date_dt:
                    raise RuntimeError(
                        f"Date range overlaps with existing event '{existing_event['title']}' "
                        f"(ID: {existing_event['event_id']}, {existing_event['start_date']} to {existing_event['end_date']})."
                    )

        years = list(range(start_date_dt.year, end_date_dt.year + 1))
        metadata_files = [MetadataFile.get_instance(year) for year in years]
        media_in_range_dfs = [
            mf.df[(mf.df['dt'].dt.date >= start_date_dt.date()) & (mf.df['dt'].dt.date <= end_date_dt.date())]
            for mf in metadata_files
        ]
        
        all_media_df = pd.concat(media_in_range_dfs) if media_in_range_dfs else pd.DataFrame()

        if not all_media_df.empty and all_media_df['event_id'].notna().any():
            media_with_event = all_media_df[all_media_df['event_id'].notna()]
            raise RuntimeError(
                f"Found {len(media_with_event)} media files that already belong to an event. "
                f"Cannot move media already assigned. Sample file: {media_with_event['filepath'].iloc[0]}"
            )

        event_id = self._next_event_id()
        event_index = _calculate_next_event_index(start_date_dt.strftime('%Y'), start_date_dt.strftime('%m'))
        event = EventEntry(event_id, event_index, start_date_dt, end_date_dt, title, description, nominal_month)
        print(f"[-] Event plan created with ID: {event.event_id}")

        if all_media_df.empty:
            print("[!] No media found in date range. Creating event entry only.")
            self.df = pd.concat([self.df, pd.DataFrame([event.to_dict()])], ignore_index=True)
            self.write()
            print(f"[-] Event '{title}' created with no associated media.")
            return event

        print(f"[-] Found {len(all_media_df)} media files to associate with the event.")
        
        # 2. EXECUTION (TRANSACTIONAL BLOCK)
        event_dir = event.get_directory()
        event_dir_created = False
        deletion_started = False
        try:
            print(f"[-] Creating event directory: {event_dir}")
            os.makedirs(event_dir, exist_ok=True)
            event_dir_created = True

            # --- COPY PHASE ---
            print("[-] Copying files...")
            path_map = {}
            for _, row in all_media_df.iterrows():
                original_filepath = row['filepath']
                filename = os.path.basename(original_filepath)
                new_filepath = os.path.join(event_dir, filename)
                shutil.copy2(original_filepath, new_filepath)
                path_map[original_filepath] = new_filepath
            print(f"[-] Successfully copied {len(path_map)} files.")

            # --- METADATA UPDATE PHASE ---
            print("[-] Updating metadata files...")
            
            # Prepare a dataframe of all the new metadata rows
            new_metadata_df = all_media_df.copy()
            new_metadata_df['filepath'] = new_metadata_df['filepath'].map(path_map)
            new_metadata_df['event_id'] = event.event_id

            # --- 1. REMOVE OLD METADATA ---
            # Group media by their original year to know which files to read/remove from.
            media_by_original_year = defaultdict(list)
            for original_path in path_map.keys():
                year = helper.get_year_from_filepath(original_path)
                media_by_original_year[year].append(original_path)

            print("[-] Removing old metadata entries...")
            for year, original_paths_in_year in media_by_original_year.items():
                mf = MetadataFile.get_instance(year)
                
                original_count = len(mf.df)
                mf.df = mf.df[~mf.df['filepath'].isin(original_paths_in_year)]
                removed_count = original_count - len(mf.df)
                
                mf.write()
                print(f"[-]  - Removed {removed_count} rows from {year} metadata.")

            # --- 2. ADD NEW METADATA ---
            # All new metadata belongs to the event's year.
            event_year = event.start_date.year
            print(f"[-] Adding new metadata entries to {event_year} metadata...")
            event_year_mf = MetadataFile.get_instance(event_year)

            original_count = len(event_year_mf.df)
            event_year_mf.df = pd.concat([event_year_mf.df, new_metadata_df], ignore_index=True)
            added_count = len(event_year_mf.df) - original_count

            event_year_mf.write()
            print(f"[-]  - Added {added_count} rows to {event_year} metadata.")

            # --- COMMIT EVENT TO CSV ---
            print("[-] Committing event to events.csv...")
            self.df = pd.concat([self.df, pd.DataFrame([event.to_dict()])], ignore_index=True)
            self.write()

            # --- DELETE ORIGINALS PHASE ---
            print("[-] Deleting original files...")
            deletion_started = True
            for original_path in path_map.keys():
                os.remove(original_path)
            print(f"[-] Successfully deleted {len(path_map)} original files.")
            
            print(f"\n[SUCCESS] Event '{title}' created successfully!")
            return event

        except Exception as e:
            # 3. ROLLBACK
            print(f"\n[!!!] ERROR: An error occurred: {e}")
            print("[!!!] Rolling back changes...")

            if deletion_started:
                print("[CRITICAL] An error occurred AFTER some original files were deleted.")
                print(f"[CRITICAL] The new event directory '{event_dir}' will NOT be deleted to prevent data loss.")
                print("[CRITICAL] Please manually verify its contents and clean up any remaining original files.")
            elif event_dir_created:
                print(f"[!!!]  - Deleting event directory: {event_dir}")
                shutil.rmtree(event_dir, ignore_errors=True)
            
            print("[!!!] Rollback complete.")
            raise


def main():
    event_metadata_file = EventsMetadataFile.get_instance()
    # event_metadata_file.create_event(
    #     title='My Test Event',
    #     start_date='2013-01-04',
    #     end_date='2014-02-01',
    # )


if __name__ == "__main__":
    main()
