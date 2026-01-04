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

## AI Usage

### Cursor CLI

1. On Windows, WSL into an Ubuntu environment (linux kernel on top of a lightweight VM) by running `wsl` in powershell.
   1. `uname -a` should show you're on a Linux WSL
   2. `lsb_release -a` should show you're on Ubuntu (Ubuntu 24.04.2 LTS in my case)
2. Then `cd` into the project directory (`cd /mnt/f/Pictures/` for example)
3. Install Cursor CLI if haven't already (https://cursor.com/docs/cli/overview)
4. `cursor-agent --model "auto"` to get started in interactive shell.

Notes:
- CLI has a limit to free usage. Not sure when this will refresh.
- CLI interface a bit clunky but usable.
- Immediately makes the change and may be hard to identify what exactly changed.

### Claude Code

1. Same steps as above for WSL
2. Install Claude Code if haven't already (https://code.claude.com/docs/en/overview)
3. `claude` to get stated in interactive shell.

### Gemini CLI

Docs: https://geminicli.com/docs/get-started/deployment/

Notes:
- Long requests seem to cut off at some point
- Responses are slow, significantly. Not sure if this is because free version only has Gemini 2.5.
- Requests user approval for each change, nice!
