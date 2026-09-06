"""
Swing by Delay VFX Script

Delays alternate incoming voices to create swing.  This implementation uses
FL Studio VFX Script's Voice callbacks: it creates a vfx.Voice, copies the
incoming voice into it, then calls trigger() and release() at the appropriate
future ticks.  It does not attempt to send synthetic MIDI dictionaries.
"""

import flvfx as vfx

DEFAULT_SWING = 50.0
SUBDIVISION_NAMES = ['Auto', '8th', '16th', '32nd', 'Custom']
SUBDIVISION_PPQ_MULTIPLIERS = {
    '8th': 0.5,
    '16th': 0.25,
    '32nd': 0.125,
}

_song_tick = 0
_active_voices = []
_note_intervals = []
_last_note_tick = None
_AUTO_INTERVAL_COUNT = 8


class SwingVoice(vfx.Voice):
    """An output voice which retains the incoming voice it was copied from."""

    parent_voice = None
    delay_ticks = 0
    trigger_count = 0
    release_count = -1
    triggered = False


def createDialog():
    form = vfx.ScriptDialog('', 'Delays every other note using VFX Voice events.')

    form.addGroup('Swing')
    form.addInputKnob('Amount', DEFAULT_SWING, 0, 100,
                      hint='Delay of alternate notes as a percentage of the selected subdivision')
    form.endGroup()

    form.addGroup('Subdivision')
    form.addInputCombo('Grid', SUBDIVISION_NAMES, 0,
                       hint='Timing grid used to select alternate notes')
    form.addInputKnobInt('Custom Ticks', 24, 1, 960,
                         hint='Ticks per subdivision when Grid is Custom')
    form.addInputCheckbox('Auto Detect', True,
                          hint='For Auto grid, estimate the grid from incoming note spacing')
    form.endGroup()

    form.addGroup('Behavior')
    form.addInputCheckbox('Preserve Length', True,
                          hint='Delay NoteOff by the same amount as its NoteOn')
    form.endGroup()
    return form


def _input(group, name):
    """VFX qualifies controls with their ScriptDialog group name."""
    return vfx.context.form.getInputValue(group + ': ' + name)


def _subdivision_ticks():
    selection = int(_input('Subdivision', 'Grid'))
    selection = max(0, min(selection, len(SUBDIVISION_NAMES) - 1))
    name = SUBDIVISION_NAMES[selection]

    if name == 'Custom':
        return max(1, int(_input('Subdivision', 'Custom Ticks')))

    if name == 'Auto':
        if bool(_input('Subdivision', 'Auto Detect')) and _note_intervals:
            ordered = sorted(_note_intervals)
            return max(1, ordered[len(ordered) // 2])
        name = '16th'

    return max(1, int(round(vfx.context.PPQ * SUBDIVISION_PPQ_MULTIPLIERS[name])))


def _remember_note_interval():
    global _last_note_tick
    if _last_note_tick is not None:
        interval = _song_tick - _last_note_tick
        if interval > 0:
            _note_intervals.append(interval)
            if len(_note_intervals) > _AUTO_INTERVAL_COUNT:
                _note_intervals.pop(0)
    _last_note_tick = _song_tick


def onTriggerVoice(incomingVoice):
    """Copy the input voice and trigger that copy now or after its swing delay."""
    _remember_note_interval()

    subdivision = _subdivision_ticks()
    step_index = _song_tick // subdivision
    delay = 0
    if step_index % 2:
        amount = float(_input('Swing', 'Amount'))
        delay = int(round(subdivision * amount / 100.0))

    voice = SwingVoice()
    voice.copyFrom(incomingVoice)
    voice.parent_voice = incomingVoice
    voice.delay_ticks = delay
    voice.trigger_count = delay + 1
    _active_voices.append(voice)

    # The +1 matches the VFX Script tick convention used by the supplied
    # Note Repeat example: the counter is decremented in subsequent onTick calls.
    if delay == 0:
        voice.trigger()
        voice.triggered = True
        voice.trigger_count = 0


def onReleaseVoice(incomingVoice):
    """Release only voices created from this incoming voice."""
    preserve_length = bool(_input('Behavior', 'Preserve Length'))

    for voice in list(_active_voices):
        if voice.parent_voice != incomingVoice:
            continue

        if preserve_length:
            # The release is offset by the exact NoteOn delay, retaining the
            # source note's duration even when it is released before triggering.
            voice.release_count = voice.delay_ticks + 1
        else:
            # Cancel an unplayed delayed note; otherwise release it immediately.
            if voice.triggered:
                voice.release()
            _active_voices.remove(voice)


def onTick():
    global _song_tick
    _song_tick += 1

    for voice in list(_active_voices):
        if not voice.triggered and voice.trigger_count > 0:
            voice.trigger_count -= 1
            if voice.trigger_count == 0:
                voice.trigger()
                voice.triggered = True

        if voice.release_count >= 0:
            voice.release_count -= 1
            if voice.release_count == 0:
                voice.release()
                _active_voices.remove(voice)