from src import constants, helper
from src.classes.EventEntry import EventEntry
from src.classes.MetadataFile import MetadataFile

import os
import glob
import pandas as pd
from datetime import datetime


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
        return event_id

    def create_event(self, title, start_date, end_date,
                     description=None, nominal_month=None) -> EventEntry:
        print(f'[*] Creating new event: {title}')
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

        # Validate date range
        if start_date > end_date:
            raise RuntimeError(
                f"Invalid date range: start_date ({start_date.strftime('%Y-%m-%d')}) must be <= end_date ({end_date.strftime('%Y-%m-%d')})"
            )

        # Check for overlapping date ranges with existing events
        if len(self.df) > 0:
            for _, existing_event in self.df.iterrows():
                existing_start = datetime.strptime(existing_event['start_date'], '%Y-%m-%d')
                existing_end = datetime.strptime(existing_event['end_date'], '%Y-%m-%d')
                
                # Check if date ranges overlap
                # Two ranges overlap if: start1 <= end2 AND start2 <= end1
                if start_date <= existing_end and existing_start <= end_date:
                    raise RuntimeError(
                        f"Date range overlaps with existing event '{existing_event['title']}' "
                        f"(ID: {existing_event['event_id']}, "
                        f"{existing_event['start_date']} to {existing_event['end_date']}). "
                        f"Only non-intersecting date ranges are supported."
                    )

        event_id = self._next_event_id()
        event_index = _calculate_next_event_index(start_date.strftime('%Y'), start_date.strftime('%m'))

        event = EventEntry(
            event_id=event_id,
            event_index=event_index,
            start_date=start_date,
            end_date=end_date,
            title=title,
            description=description,
            nominal_month=nominal_month,
        )
        print(f"[-] EventEntry created:")
        print(event)

        # update events metadata file
        new_df = pd.DataFrame([event.to_dict()], columns=constants.EVENTS_COLS)
        self.df = pd.concat([self.df, new_df], ignore_index=True)
        self.write()
        print(f"[-] Event Metadata file updated!")

        # identify media in range (NOTE: edge case where this spans multiple years)
        years = list(range(start_date.year, end_date.year + 1))
        metadata_files = [MetadataFile.get_instance(year) for year in years]
        media_in_range = [
            metadata_file.df[(metadata_file.df['dt'].dt.date >= start_date.date()) &
                             (metadata_file.df['dt'].dt.date <= end_date.date())]
            for metadata_file in metadata_files
        ]
        
        # Check if any media already belongs to an event
        # Handle case where media_in_range might be empty or contain only empty DataFrames
        if media_in_range and any(len(df) > 0 for df in media_in_range):
            all_media_in_range = pd.concat(media_in_range)
        else:
            all_media_in_range = pd.DataFrame([], columns=constants.METADATA_COLS)
        
        media_with_existing_event = all_media_in_range[all_media_in_range['event_id'].notna()] if len(all_media_in_range) > 0 else pd.DataFrame([], columns=constants.METADATA_COLS)
        
        if len(media_with_existing_event) > 0:
            existing_event_ids = media_with_existing_event['event_id'].unique()
            filepaths = media_with_existing_event['filepath'].tolist()[:10]  # Show first 10
            raise RuntimeError(
                f"Found {len(media_with_existing_event)} media files that already belong to event(s) {existing_event_ids.tolist()}. "
                f"Cannot move media that is already assigned to an event. "
                f"Please investigate and remove media from existing events first. "
                f"Sample filepaths: {filepaths}"
            )
        
        num_media_in_range = sum(len(df) for df in media_in_range)
        if num_media_in_range == 0:
            print(f"[!!!] WARNING: Could not find any media in range of dates: {start_date.strftime('%Y-%m-%d')} -> {end_date.strftime('%Y-%m-%d')}!")
        else:
            print(f"[-] Found {num_media_in_range} media in range of dates: {start_date.strftime('%Y-%m-%d')} -> {end_date.strftime('%Y-%m-%d')}!")

        # create events directory
        os.makedirs(event.get_directory(), exist_ok=True)

        # move media
        def _helper_construct_event_media_filepath(old_filepath):
            filename = helper.decompose_filepath(old_filepath)['filename']
            return os.path.join(event.get_directory(), filename)

        new_metadata = pd.concat(media_in_range)
        new_metadata['new_filepath'] = new_metadata['filepath'].apply(_helper_construct_event_media_filepath)
        for _, row in new_metadata.iterrows():
            os.rename(row['filepath'], row['new_filepath'])

        # remove old metadata
        for metadata_file, in_range in zip(metadata_files, media_in_range):
            metadata_file.df = metadata_file.df[~metadata_file.df['filepath'].isin(in_range['filepath'])]
            metadata_file.write()

        # add new metadata (filepath & event_id)
        event_year = start_date.year
        mf = MetadataFile.get_instance(event_year)
        new_metadata['filepath'] = new_metadata['new_filepath']
        new_metadata['event_id'] = event_id
        mf.df = pd.concat([mf.df, new_metadata[constants.METADATA_COLS]])
        mf.write()

        print(f"[-] Event successfully created!")
        return event


def main():
    event_metadata_file = EventsMetadataFile.get_instance()
    # event_metadata_file.create_event(
    #     title='My Test Event',
    #     start_date='2025-09-14',
    #     end_date='2025-09-14',
    # )


if __name__ == "__main__":
    main()
