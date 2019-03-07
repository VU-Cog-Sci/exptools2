import os.path as op
import pandas as pd
import numpy as np
from exptools2.session import Session
from exptools2.trial import Trial
from psychopy.visual import ImageStim


class FLocTrial(Trial):
    """ Simple trial with text (trial x) and fixation. """
    def __init__(self, session, trial_nr, phase_durations, pic=None, **kwargs):
        super().__init__(session, trial_nr, phase_durations, **kwargs)

        if pic == 'baseline':
            self.pic = self.session.default_fix
        else:
            spath = op.join(self.session.stim_dir, pic.split('-')[0], pic)
            self.pic = ImageStim(self.session.win, spath) 

    def draw(self):
        """ Draws stimuli """

        if self.phase == 0:
            self.pic.draw()
        else:
            if isinstance(self.pic, ImageStim):
                pass
            else:
                self.session.default_fix.draw()


class FLocSession(Session):
    """ Simple session with x trials. """
    def __init__(self, output_str, stim_file, stim_dir, rt_cutoff=1,
                 settings_file=None):
        """ Initializes TestSession object. """

        self.stim_file = stim_file
        self.stim_df = pd.read_csv(stim_file, sep='\t')
        self.stim_dir = stim_dir
        self.rt_cutoff = rt_cutoff

        self.trials = []
        self.current_trial = None
        super().__init__(output_str, settings_file)

    def create_trial(self, trial_nr):
        
        trial = FLocTrial(
            session=self,
            trial_nr=trial_nr,
            phase_durations=(0.4, 0.1),
            pic=self.stim_df.loc[trial_nr, 'stim_name'],
            load_next_during_phase=1,
            verbose=True,
            timing='seconds'
        )
        self.trials.append(trial)
        self.current_trial = trial

    def run(self):
        """ Runs experiment. """

        watching_response = False
        self.create_trial(trial_nr=0)
        self.display_text('Waiting for scanner', keys=self.settings['mri'].get('sync', 't'))
        self.start_experiment()

        hits = []
        for trial_nr in range(self.stim_df.shape[0]):

            if self.stim_df.loc[trial_nr, 'task_probe'] == 1:
                watching_response = True
                onset_watching_response = self.clock.getTime()

            self.current_trial.run()

            if watching_response:

                if self.trials[-2].last_resp is None: # No answer given
                    if (self.clock.getTime() - onset_watching_response) > self.rt_cutoff:
                        hits.append(0)  # too late!
                        watching_response = False
                    else:
                        pass  # keep on watching
                else:  # answer was given
                    rt = self.trials[-2].last_resp_onset - onset_watching_response
                    print(f'Reaction time: {rt:.5f}')
                    if rt > self.rt_cutoff:  # too late!
                        hits.append(0)
                    else:  # on time! (<1 sec after onset 1-back stim)
                        hits.append(1)
                    watching_response = False

        mean_hits = np.mean(hits) * 100
        txt = f'{mean_hits:.1f}% correct ({sum(hits)} / {len(hits)})!'
        self.display_text(txt, duration=1)
        self.close()