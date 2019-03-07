import os.path as op
from exptools2.experiments import FLocSession

this_dir = op.abspath(op.dirname(__file__))
stim_dir = op.join(op.dirname(op.dirname(this_dir)), 'fLoc', 'stimuli')
session = FLocSession('sub-01', stim_file=op.join(this_dir, 'fLoc_trials.tsv'),
                           stim_dir=stim_dir)
session.run()