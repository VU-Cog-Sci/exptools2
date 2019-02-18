import yaml
import os.path as op
import numpy as np
import pandas as pd
from psychopy.iohub import launchHubServer
from psychopy.visual import Window, Circle, TextStim
from psychopy.event import waitKeys, Mouse
from psychopy.core import Clock, getTime
from psychopy.monitors import Monitor
from psychopy import logging
from psychopy.hardware.emulator import SyncGenerator


class Session:

    def __init__(self, settings_file=None, eyetracker_on=False):
        self.settings_file = settings_file
        self.eyetracker_on=eyetracker_on
        self.clock = Clock()
        self.timer = Clock()
        self.start_exp = None
        self.current_trial = None
        self.log = []
        self.logfile = logging.LogFile(f='log.txt', filemode='w', level=logging.EXP)

        # Initialize
        self.settings = self._load_settings()
        self.monitor = self._create_monitor()
        self.win = self._create_window()
        self.mouse = Mouse(**self.settings['mouse'])
        self.default_fix = Circle(self.win, radius=0.01, fillColor='white', edges=1000)
        self.mri_simulator = self._setup_mri_simulator() if self.settings['mri']['simulate'] else None
        self.tracker = None

    def _load_settings(self):

        if self.settings_file is None:
            self.settings_file = op.join(op.dirname(__file__), 'default_settings.yml')
            logging.warn(f"Using default logfile ({self.settings_file}")

        with open(self.settings_file, 'r') as f_in:
            return yaml.load(f_in)

    def _create_monitor(self):
        monitor = Monitor(**self.settings['monitor'])
        monitor.save()  # needed for iohub eyetracker
        return monitor

    def _create_window(self):
        win = Window(monitor=self.monitor, **self.settings['window'])
        return win

    def _setup_mri_simulator(self):
        args = self.settings['mri'].copy()
        args.pop('simulate')
        return SyncGenerator(**args)

    def start_experiment(self):
        self.start_exp = getTime()  # abs time
        self.clock.reset()
        self.timer.reset()

        if self.mri_simulator is not None:
            self.mri_simulator.start()

    def display_text(self, text, keys=['return'], **kwargs):
        stim = TextStim(self.win, text=text, **kwargs)
        stim.draw()
        self.win.flip()
        waitKeys(keyList=keys)

    def close(self):
        self.exp_stop = self.clock.getTime()
        print(f"Duration experiment: {self.exp_stop:.3f}\n")
        self.log = pd.concat(self.log)
        self.log['onset_abs'] = self.log['onset'] + self.start_exp
        print(self.log)

        if self.mri_simulator is not None:
            self.mri_simulator.stop()

    def init_eyetracker(self):

        if not self.eyetracker_on:
            raise ValueError("Cannot initialize eyetracker if eyetracker_on=False!")

        EYETRACKER_NAME = 'eyetracker.hw.sr_research.eyelink.EyeTracker'
        # default_native_data_file_name: et_data
        self.iohub = launchHubServer(
            psychopy_monitor_name=self.monitor.name,
            datastore_name='test_et',
            **{EYETRACKER_NAME: {
                'enable_interface_without_connection': True
            }}
        )

        self.tracker = self.iohub.getDevice('eyetracker.hw.sr_research.eyelink.EyeTracker')

    def start_recording_eyetracker(self):
        self.tracker.setRecordingState(True)

    def stop_recording_eyetracker(self):
        self.tracker.setRecordingState(False)

    def calibrate_eyetracker(self):
        self.tracker.runSetupProcedure()

    def close_tracker(self):
        self.stop_recording_eyetracker()
        self.iohub.quit()
