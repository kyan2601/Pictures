# Pictures File System

## File Naming Conventions

### Media File Naming

The file naming structure will be of the form *[yymmdd][img_num].[ext]*.
The image number is a three-digit, zero-padded number.
An example of this base structure would be as follows: *240207001.jpeg*.

This structure is meant for compactness, not necessarily human readability.
To introduce some more context around the image contents or meaning, include a title for the image.

An image with a title will following the naming convention of *[yymmdd][img_num]_[title].[ext]*.
The expectation is to split on underscore and period to extract the title.
An example would be: *231231012_Christmas_Party.png*.

### Folder Naming

The image folder hierarchy is as follows:
1. Year
2. Month or Event
3. Image

A sample of this would be:
- 2024
  - 01
  - 01_1_January_New_Years_Party
  - 01_2_January_Vacation_Trip
  - 02
- 2023
  - 09
  - 10
  - 10_1_October_Yosemite
  - 11

The event folder naming structure is laid out as *[mm]_[event_num]_[month_name]_[title]*.
*[mm]* is the month of the first day in the event to ensure chronological order.
*[event_num]* is used as a tracker to keep all the events chronologically organized within each month.
*[month_name]* is the nominal month that is generally associated with this event.
It will typically be the month that this event lies the most in.
Note that this can be different from *[mm]*, the start month.
Finally, we wrap up with the title of the event.
