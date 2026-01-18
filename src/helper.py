import glob
import os
import re
from datetime import datetime

import pandas as pd
from geopy.geocoders import Nominatim

from src import constants


#####################################
# FUNCTIONAL
#####################################


def try_except(success, failure, *exceptions):
    """
    Try to execute success(), return failure() or failure value on exception.
    
    Args:
        success: Callable to execute
        failure: Callable to execute on exception, or value to return
        *exceptions: Exception types to catch (defaults to Exception if none provided)
    """
    try:
        return success()
    except exceptions if exceptions else Exception:
        return failure() if callable(failure) else failure


#####################################
# LOGICAL
#####################################


def keyword_is_name(keyword):
    """
    Check if a keyword matches the pattern of a person's name (e.g., "JohnSmith").
    
    Args:
        keyword: String to check
        
    Returns:
        bool: True if keyword matches name pattern
    """
    return bool(re.match("[A-Z][a-z]+[A-Z][a-z]+", keyword))


#####################################
# FILE SYSTEM
#####################################


def get_filepaths_by_directory(directory=constants.ROOT_DIR, ignore_new_media=True) -> list[str]:
    """
    Get all media file paths from a directory recursively.
    
    Args:
        directory: Directory to search (defaults to ROOT_DIR)
        ignore_new_media: If True, exclude files from NEW_MEDIA_DIR
        
    Returns:
        list[str]: Sorted list of unique file paths
    """
    filepaths = []

    for ext in constants.MEDIA_EXTENSIONS:
        filepaths.extend(glob.glob(os.path.join(directory, '**', f'*.{ext}'), recursive=True))

    if ignore_new_media:
        filepaths = [filepath for filepath in filepaths if not filepath.startswith(constants.NEW_MEDIA_DIR)]

    return sorted(list(set(filepaths)))


def decompose_filepath(filepath):
    """
    Decompose a filepath into its components.
    
    Args:
        filepath: Full file path
        
    Returns:
        dict: Dictionary with 'dirname', 'filename', 'filename_without_ext', 'ext'
    """
    dirname = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    filename_without_ext, ext = filename.rsplit('.', 1)

    return {
        'dirname': dirname,
        'filename': filename,
        'filename_without_ext': filename_without_ext,
        'ext': ext,
    }


def decompose_filename(filename):
    """
    Decompose a media filename following the naming convention [yymmdd][img_num]_[title].[ext].
    
    Args:
        filename: Filename to decompose (e.g., "240207001_Christmas_Party.jpeg")
        
    Returns:
        dict: Dictionary with 'date', 'date_obj', 'media_index', 'title', 'title_clean', 'ext'
    """
    filename_without_ext, ext = filename.rsplit('.', 1)
    date = filename_without_ext[:6]
    dt = datetime.strptime('20' + date, '%Y%m%d').date()
    media_index = int(filename_without_ext[6:9])

    title = None
    title_clean = None
    if '_' in filename_without_ext:
        # has title
        _, title = filename_without_ext.split('_', 1)
        title_clean = title.replace('_', ' ')

    return {
        'date': date,
        'date_obj': dt,
        'media_index': media_index,
        'title': title,
        'title_clean': title_clean,
        'ext': ext,
    }


def is_new_media(filepath):
    dirname = decompose_filepath(filepath)['dirname']
    if constants.NEW_MEDIA_DIR in dirname:
        return True
    return False


def get_year_from_filepath(filepath):
    if is_new_media(filepath):
        raise RuntimeError(f"Tried to call get_year_from_filepath() on filepath [{filepath}]")

    dirname = decompose_filepath(filepath)['dirname']
    try:
        relative_path = dirname.replace(constants.ROOT_DIR, '').strip(os.sep)
        year = int(relative_path[:4])
    except Exception as e:
        raise RuntimeError(f"Could not extract year from filepath [{filepath}]: {e}")
    return year


def get_directory_for_year(year):
    return str(os.path.join(constants.ROOT_DIR, str(year)))


def get_directory_for_year_month(year, month):
    return str(os.path.join(constants.ROOT_DIR, str(year), str(month).zfill(2)))


#####################################
# BACKUP
#####################################


def create_backup_directory(action_type: str) -> str:
    """
    Creates a unique, timestamped backup directory for a specific action.

    Args:
        action_type (str): A string representing the type of action (e.g., 'create_event').

    Returns:
        str: The full path to the newly created backup directory.
    """
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    backup_dir_name = f"{timestamp}_{action_type}"
    backup_dir_path = os.path.join(constants.BACKUP_DIR, backup_dir_name)
    
    print(f"[-] Creating backup directory: {backup_dir_path}")
    os.makedirs(backup_dir_path, exist_ok=True)
    
    return backup_dir_path


#####################################
# SERIALIZATION
#####################################

def serialize_filepath(filepath, delimiter='|/'):
    """
    Serialize a filepath for storage in CSV (replaces path separators with delimiter).
    
    Args:
        filepath: Full file path
        delimiter: Delimiter to use (default: '|/')
        
    Returns:
        str: Serialized filepath
    """
    return delimiter.join(filepath.replace(constants.ROOT_DIR, '').strip(os.sep).split(os.sep))


def deserialize_filepath(filepath, delimiter='|/'):
    """
    Deserialize a filepath from CSV format back to full path.
    
    Args:
        filepath: Serialized filepath
        delimiter: Delimiter used in serialization (default: '|/')
        
    Returns:
        str: Full file path
    """
    return os.sep.join([constants.ROOT_DIR] + filepath.split(delimiter))


#####################################
# GEOLOGICAL
#####################################


def _gps_coordinates_helper(ref, coordinate):
    multiplier = 1.0 if ref in ['N', 'E'] else -1.0
    return multiplier * sum(x / 60**n for n, x in enumerate(coordinate))


def gps_coordinates_to_lat_long(gps_latitude_ref, gps_latitude, gps_longitude_ref, gps_longitude):
    return (
        _gps_coordinates_helper(gps_latitude_ref, gps_latitude),
        _gps_coordinates_helper(gps_longitude_ref, gps_longitude)
    )


def lat_long_parser(location):
    match = re.findall(r'([+-][\d.]+)', location)
    return (
        float(match[0]) if len(match) >= 2 else pd.NA,
        float(match[1]) if len(match) >= 2 else pd.NA,
        float(match[2]) if len(match) > 2 else pd.NA,
    )


def lat_long_to_address(lat, long):
    # limit of 1 request per second to Nominatim API
    geolocator = Nominatim(user_agent="PictureIndexingServices")
    location = geolocator.reverse(f"{lat},{long}")
    address = location.raw['address']
    # of interest: suburb, city, county, state, postcode, country
    return address
