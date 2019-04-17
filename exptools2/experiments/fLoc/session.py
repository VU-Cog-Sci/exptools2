import os.path as op
import pandas as pd
import numpy as np
from psychopy.visual import ImageStim
from ...core import Session, Trial


class FLocTrial(Trial):
    """ Simple trial with text (trial x) and fixation. """
    def __init__(self, session, trial_nr, phase_durations, pic=None, **kwargs):
        super().__init__(session, trial_nr, phase_durations, **kwargs)

        if pic == 'baseline':
            self.to_draw = self.session.default_fix
        else:
            spath = op.join(self.session.stim_dir, 'stimuli', pic.split('-')[0], pic)
            self.session.current_stim.setImage(spath)
            self.to_draw = self.session.current_stim

    def draw(self):
        """ Draws stimuli """

        if self.phase == 0:
            self.to_draw.draw()
        else:
            if isinstance(self.to_draw, ImageStim):
                pass
            else:
                self.session.default_fix.draw()


class FLocSession(Session):
    """ Simple session with x trials. """
    def __init__(self, sub, run, output_str, stim_dir, scrambled, dummies,
                 ntrials=None, rt_cutoff=1, output_dir=None, settings_file=None):
        """ Initializes TestSession object. """

        msg = ("When using this localizer, please acknowledge the original "
               "creators of the task (Stigliani et al.); for more info "
               "about how to cite the original authors, check "
               "http://vpnl.stanford.edu/fLoc\n")
        print(msg)

        if not op.isdir(stim_dir):
            msg = (f"Directory {stim_dir} does not exist!\n"
                   f"To get the stimuli, simply run the following:\n"
                   f"git clone https://github.com/FEED-UvA/fLoc.git")
            raise OSError(msg)
            
        self.stim_dir = stim_dir
        self.scrambled = scrambled
        self.dummies = dummies
        self.ntrials = ntrials
        self.rt_cutoff = rt_cutoff

        trials_dir = op.join(op.dirname(op.dirname(op.dirname(__file__))), 'data')
        if scrambled:
            stim_file =  op.join(trials_dir, 'fLoc_trials_with_scrambled.tsv')
        else:
            stim_file =  op.join(trials_dir, 'fLoc_trials.tsv')

        df = pd.read_csv(stim_file, sep='\t')
        sub_id = f'sub-{sub}'
        self.stim_df = df.query('sub_id == @sub_id & run == @run')
        
        if self.ntrials is not None:  # just for debugging
            self.stim_df = self.stim_df.iloc[:self.ntrials, :]

        self.stim_df.index = np.arange(0, len(self.stim_df), dtype=int)
        self.trials = []
        self.current_trial = None

        super().__init__(output_str=output_str, settings_file=settings_file,
                         output_dir=output_dir)

        self.current_stim = ImageStim(self.win, image=None)
        self.type2condition = dict(child='face', adult='face',
                                   body='body', limb='body',
                                   corridor='place', house='place',
                                   word='character', number='character',
                                   instrument='object', car='object',
                                   scrambled='scrambled', scrambled1='scrambled',
                                   scrambled2='scrambled', baseline='')

    def create_trial(self, trial_nr):
        
        if trial_nr == (self.stim_df.shape[0] - 1):  # last trial!
            load_next_during_phase = None
        else:
            load_next_during_phase = 1

        stim_type = self.stim_df.loc[trial_nr, 'trial_type']
        stim_name = self.stim_df.loc[trial_nr, 'stim_name']
        task_probe = self.stim_df.loc[trial_nr, 'task_probe']

        trial = FLocTrial(
            session=self,
            trial_nr=trial_nr,
            phase_durations=(0.4, 0.1),
            phase_names=(stim_type, 'ISI'),
            pic=stim_name,
            load_next_during_phase=load_next_during_phase,
            verbose=True,
            timing='seconds',
            parameters={'trial_type': self.type2condition[stim_type],
                        'stim_name': stim_name, 'task_probe': task_probe}
        )

        self.trials.append(trial)

    def run(self):
        """ Runs experiment. """

        watching_response = False
        self.create_trial(trial_nr=0)
        txt = ('Deze run duurt ongeveer 5 minutes.\n\n'
               'Als je precies hetzelfde plaatje twee keer achter elkaar ziet\n'
               'druk dan met je rechter wijsvinger op de knop.\n\n'
               'Blijf zo stil mogelijk liggen tijdens (en na) de scan!')
        self.display_text(txt, keys=self.settings['mri'].get('sync', 't'), height=0.5)
        self.start_experiment(wait_n_triggers=self.dummies)

        hits = []
        for trial_nr in range(self.stim_df.shape[0]):

            if self.stim_df.loc[trial_nr, 'task_probe'] == 1:
                watching_response = True
                onset_watching_response = self.clock.getTime()

            self.trials[trial_nr].run()

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

        mean_hits = np.mean(hits) * 100 if hits else 0
        #txt = f'{mean_hits:.1f}% correct ({sum(hits)} / {len(hits)})!'
        #self.display_text(txt, duration=1)
        fname = op.join(self.output_dir, self.output_str + '_accuracy.txt')
        with open(fname, 'w') as f_out:
            f_out.write(f'{mean_hits:.3f}')

        self.close()