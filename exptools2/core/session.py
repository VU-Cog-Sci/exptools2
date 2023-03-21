import os
import yaml
import collections
import os.path as op
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from psychopy import core
from psychopy.sound import Sound
from psychopy.hardware.emulator import SyncGenerator
from psychopy.visual import Window, TextStim
from psychopy.event import waitKeys, Mouse
from psychopy.monitors import Monitor
from psychopy import logging
from psychopy import prefs as psychopy_prefs
from ..stimuli import create_circle_fixation


class Session:
    """Base Session class"""

    def __init__(self, output_str, output_dir=None, settings_file=None):
        """Initializes base Session class.

        parameters
        ----------
        output_str : str
            Name (string) for output-files (e.g., 'sub-01_ses-post_run-1')
        output_dir : str
            Path to output-directory. Default: $PWD/logs.
        settings_file : str
            Path to settings file. If None, exptools2's default_settings.yml is used

        attributes
        ----------
        settings : dict
            Dictionary with settings from yaml
        clock : psychopy Clock
            Global clock (reset to 0 at start exp)
        timer : psychopy Clock
            Timer used to time phases
        exp_start : float
            Time at actual start of experiment
        log : psychopy Logfile
            Logfile with info about exp (level >= EXP)
        nr_frames : int
            Counter for number of frames for each phase
        win : psychopy Window
            Current window
        default_fix : TextStim
            Default fixation stim (a TextStim with '+')
        actual_framerate : float
            Estimated framerate of monitor
        """
        self.output_str = output_str
        self.output_dir = (
            op.join(os.getcwd(), "logs") if output_dir is None else output_dir
        )
        self.settings_file = settings_file
        self.clock = core.Clock()
        self.timer = core.Clock()
        self.exp_start = None
        self.exp_stop = None
        self.current_trial = None
        self.global_log = pd.DataFrame(
            columns=[
                "trial_nr",
                "onset",
                "event_type",
                "phase",
                "response",
                "nr_frames",
            ]
        )
        self.nr_frames = 0  # keeps track of nr of nr of frame flips
        self.first_trial = True
        self.closed = False

        # Initialize
        self.settings = self._load_settings()
        self.monitor = self._create_monitor()
        self.win = self._create_window()
        self.width_deg = 2 * np.degrees(
            np.arctan(self.monitor.getWidth() / self.monitor.getDistance())
        )
        self.pix_per_deg = self.win.size[0] / self.width_deg
        self.mouse = Mouse(**self.settings["mouse"])
        self.logfile = self._create_logfile()
        self.default_fix = create_circle_fixation(
            self.win, radius=0.075, color=(1, 1, 1)
        )
        self.mri_trigger = None  # is set below
        self.mri_simulator = self._setup_mri()

    def _load_settings(self):
        """Loads settings and sets preferences."""
        default_settings_path = op.join(
            op.dirname(op.dirname(__file__)), "data", "default_settings.yml"
        )
        with open(default_settings_path, "r", encoding="utf8") as f_in:
            default_settings = yaml.safe_load(f_in)

        if self.settings_file is None:
            settings = default_settings
            logging.warn("No settings-file given; using default logfile")
        else:
            if not op.isfile(self.settings_file):
                raise IOError(f"Settings-file {self.settings_file} does not exist!")

            with open(self.settings_file, "r", encoding="utf8") as f_in:
                user_settings = yaml.safe_load(f_in)

            # Update (and potentially overwrite) default settings
            _merge_settings(default_settings, user_settings)
            settings = default_settings

        # Write settings to sub dir
        if not op.isdir(self.output_dir):
            os.makedirs(self.output_dir)

        settings_out = op.join(self.output_dir, self.output_str + "_expsettings.yml")
        with open(settings_out, "w") as f_out:  # write settings to disk
            yaml.dump(settings, f_out, indent=4, default_flow_style=False)

        exp_prefs = settings["preferences"]  # set preferences globally
        for preftype, these_settings in exp_prefs.items():
            for key, value in these_settings.items():
                pref_subclass = getattr(psychopy_prefs, preftype)
                pref_subclass[key] = value
                setattr(psychopy_prefs, preftype, pref_subclass)

        return settings

    def _create_monitor(self):
        """Creates the monitor based on settings and save to disk."""
        monitor = Monitor(**self.settings["monitor"])
        monitor.setSizePix(self.settings["window"]["size"])
        monitor.save()  # needed for iohub eyetracker
        return monitor

    def _create_window(self):
        """Creates a window based on the settings and calculates framerate."""
        win = Window(monitor=self.monitor.name, **self.settings["window"])
        win.flip(clearBuffer=True)
        self.actual_framerate = win.getActualFrameRate()
        if self.actual_framerate is None:
            logging.warn("framerate not measured, substituting 60 by default")
            self.actual_framerate = 60.0
        t_per_frame = 1.0 / self.actual_framerate

        logging.warn(
            f"Actual framerate: {self.actual_framerate:.5f} "
            f"(1 frame = {t_per_frame:.5f})"
        )
        return win

    def _create_logfile(self):
        """Creates a logfile."""
        log_path = op.join(self.output_dir, self.output_str + "_log.txt")
        return logging.LogFile(f=log_path, filemode="w", level=logging.EXP)

    def _setup_mri(self):
        """Initializes an MRI simulator"""
        args = self.settings["mri"].copy()
        self.mri_trigger = self.settings["mri"]["sync"]
        if args["simulate"]:
            args.pop("simulate")
            return SyncGenerator(**args)
        else:
            return None

    def start_experiment(self, wait_n_triggers=None, show_fix_during_dummies=True):
        """Logs the onset of the start of the experiment.

        Parameters
        ----------
        wait_n_triggers : int (or None)
            Number of MRI-triggers ('syncs') to wait before actually
            starting the experiment. This is useful when you have
            'dummy' scans that send triggers to the stimulus-PC.
            Note: clock is still reset right after calling this
            method.
        show_fix_during_dummies : bool
            Whether to show a fixation cross during dummy scans.
        """
        self.exp_start = self.clock.getTime()
        self.clock.reset()  # resets global clock
        self.timer.reset()  # phase-timer

        if self.mri_simulator is not None:
            self.mri_simulator.start()

        self.win.recordFrameIntervals = True

        if wait_n_triggers is not None:
            print(f"Waiting {wait_n_triggers} triggers before starting ...")
            n_triggers = 0

            if show_fix_during_dummies:
                self.default_fix.draw()
                self.win.flip()

            while n_triggers < wait_n_triggers:
                waitKeys(keyList=[self.settings["mri"].get("sync", "t")])
                n_triggers += 1
                msg = f"\tOnset trigger {n_triggers}: {self.clock.getTime(): .5f}"
                msg = msg + "\n" if n_triggers == wait_n_triggers else msg
                print(msg)

            self.timer.reset()

    def _set_exp_stop(self):
        """Called on last win.flip(); timestamps end of exp."""
        self.exp_stop = self.clock.getTime()

    def display_text(self, text, keys=None, duration=None, **kwargs):
        """Displays text on the window and waits for a key response.
        The 'keys' and 'duration' arguments are mutually exclusive.

        parameters
        ----------
        text : str
            Text to display
        keys : str or list[str]
            String (or list of strings) of keyname(s) to wait for
        kwargs : key-word args
            Any (set of) parameter(s) passed to TextStim
        """
        if keys is None and duration is None:
            raise ValueError("Please set either 'keys' or 'duration'!")

        if keys is not None and duration is not None:
            raise ValueError("Cannot set both 'keys' and 'duration'!")

        stim = TextStim(self.win, text=text, **kwargs)
        stim.draw()
        self.win.flip()

        if keys is not None:
            waitKeys(keyList=keys)

        if duration is not None:
            core.wait(duration)

    def close(self):
        """'Closes' experiment. Should always be called, even when
        experiment is quit manually (saves onsets to file)."""

        if self.closed:  # already closed!
            return None

        self.win.callOnFlip(self._set_exp_stop)
        self.win.flip()
        self.win.recordFrameIntervals = False

        print(f"\nDuration experiment: {self.exp_stop:.3f}\n")

        if not op.isdir(self.output_dir):
            os.makedirs(self.output_dir)

        self.global_log = pd.DataFrame(self.global_log).set_index("trial_nr")
        self.global_log["onset_abs"] = self.global_log["onset"] + self.exp_start

        # Only non-responses have a duration
        nonresp_idx = ~self.global_log.event_type.isin(["response", "trigger", "pulse"])
        last_phase_onset = self.global_log.loc[nonresp_idx, "onset"].iloc[-1]
        dur_last_phase = self.exp_stop - last_phase_onset
        durations = np.append(
            self.global_log.loc[nonresp_idx, "onset"].diff().values[1:], dur_last_phase
        )
        self.global_log.loc[nonresp_idx, "duration"] = durations

        # Same for nr frames
        nr_frames = np.append(
            self.global_log.loc[nonresp_idx, "nr_frames"].values[1:], self.nr_frames
        )
        self.global_log.loc[nonresp_idx, "nr_frames"] = nr_frames.astype(int)

        # Round for readability and save to disk
        self.global_log = self.global_log.round(
            {"onset": 5, "onset_abs": 5, "duration": 5}
        )
        f_out = op.join(self.output_dir, self.output_str + "_events.tsv")
        self.global_log.to_csv(f_out, sep="\t", index=True)

        # Create figure with frametimes (to check for dropped frames)
        fig, ax = plt.subplots(figsize=(15, 5))
        ax.plot(self.win.frameIntervals)
        ax.axhline(1.0 / self.actual_framerate, c="r")
        ax.axhline(
            1.0 / self.actual_framerate + 1.0 / self.actual_framerate, c="r", ls="--"
        )
        ax.set(
            xlim=(0, len(self.win.frameIntervals) + 1),
            xlabel="Frame nr",
            ylabel="Interval (sec.)",
            ylim=(-0.01, 0.125),
        )
        fig.savefig(op.join(self.output_dir, self.output_str + "_frames.pdf"))

        if self.mri_simulator is not None:
            self.mri_simulator.stop()

        self.win.close()
        self.closed = True

    def quit(self):
        """Quits Python tread (and window if necessary)."""

        if not self.closed:
            self.close()

        core.quit()


def _merge_settings(default, user):
    """Recursive dict merge. Inspired by dict.update(), instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The merge_dct is merged into
    Adapted from https://gist.github.com/angstwad/bf22d1822c38a92ec0a9.

    Parameters
    ----------
    default : dict
        To-be-updated dict
    user : dict
        Dict to merge in default

    Returns
    -------
    None
    """
    for k, v in user.items():
        if (
            k in default
            and isinstance(default[k], dict)
            and isinstance(user[k], collections.abc.Mapping)
        ):
            _merge_settings(default[k], user[k])
        else:
            default[k] = user[k]
