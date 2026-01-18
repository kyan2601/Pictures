from src import constants, helper

import re
import os
from datetime import datetime


class EventEntry:

    def __init__(self, event_id, event_index, start_date, end_date, title,
                 description=None, nominal_month=None):
        self.event_id = event_id
        self.event_index = event_index
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d') if type(start_date) is str else start_date
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d') if type(end_date) is str else end_date
        self.title = title
        self.description = description
        self.nominal_month = nominal_month.title() if nominal_month else self.start_date.strftime('%B')

    def __str__(self):
        return "\n".join([
            f"----- Event [{self.title}] -----",
            f"Event ID: {self.event_id}",
            f"Event Index: {self.event_index}",
            f"Start Date: {self.start_date.strftime('%Y-%m-%d')}",
            f"End Date: {self.end_date.strftime('%Y-%m-%d')}",
            f"Nominal Month: {self.nominal_month}",
            f"Description: {self.description}",
            f"---------------",
        ])

    def __lt__(self, other):
        return self.event_id < other.event_id

    def __gt__(self, other):
        return self.event_id > other.event_id

    def __eq__(self, other):
        return self.event_id == other.event_id

    def to_dict(self):
        data = {k: v for k, v in vars(self).items() if k in constants.EVENTS_COLS}
        data['start_date'] = self.start_date.strftime('%Y-%m-%d')
        data['end_date'] = self.end_date.strftime('%Y-%m-%d')
        return data

    def get_directory(self):
        year = self.start_date.strftime('%Y')
        month = self.start_date.strftime('%m')
        title = re.sub(r'[^A-Za-z0-9\s]', '', self.title).replace(' ', '_')
        folder_name = f'{month}_{self.event_index}_{self.nominal_month}_{title}'
        return str(os.path.join(helper.get_directory_for_year(year), folder_name))
