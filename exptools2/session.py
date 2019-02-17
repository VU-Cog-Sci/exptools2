import numpy as np
import pandas as pd
from psychopy.iohub import launchHubServer
from psychopy.visual import Window, Circle, TextStim
from psychopy.event import waitKeys
from psychopy.core import Clock


class Session:

    def __init__(self, eyetracker_on=False):
        self.eyetracker_on=eyetracker_on
        self.phase_durations = []
        self.clock = Clock()
        self.win = Window()
        self.default_fix = Circle(self.win, radius=0.01, fillColor='white', edges=1000)
        self.params = []
        self.exp_stop = None
        self.stimuli = None
        self.current_trial = None

    def start_experiment(self):
        self.clock.reset()

    def display_text(text, keys=['return']):
        stim = TextStim(self.win, text=text)
        stim.draw()
        self.win.flip()
        waitKeys(keyList=keys)

    def close(self):
        self.exp_stop = self.clock.getTime()
        print("Duration experiment: %.3f\n" % self.exp_stop)
        self.params = pd.concat(self.params)
        print(self.params)

        #deviations = self.params['onset'] - self.params['onset_intended']
        #mae = np.abs(deviations.values).mean()
        #print("Mean absolute deviation in onsets: %.4f" % mae)

    def init_tracker(self):

        if not self.eyetracker_on:
            raise ValueError("Cannot initialize eyetracker if eyetracker_on=False!")

        self.iohub = launchHubServer()  # add Display with params from settings.yml
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
