import collections

class StreamBinding(object):
  """
  The StreamBinding class is Tarrasque's metaphor for the replay. Every
  Tarrasque entity class has a reference to an instance of this
  class, and when the tick of the instance changes, the data returned by
  those classes changes. This makes it easy to handle complex object graphs
  without explicitly needing to pass the Skadi demo object around.

  .. note:: Where methods on this class take absolute tick values (i.e. the
     ``start`` and ``end`` arguments to :meth:`iter_ticks`), special string
     arguments may be passed. These are:

     * ``"start"`` - The start of the replay
     * ``"draft"`` - The start of the draft
     * ``"pregame"`` - The end of the draft phase
     * ``"game"`` - The time when the game clock hits 0
     * ``"postgame"`` - The time the ancient is destroyed
     * ``"end"`` - The last tick in the replay

     These values will not be 100% accurate, but should be good +-50 ticks
  """

  @property
  def user_messages(self):
    """
    The user messages for the current tick.
    """
    return self._user_messages

  @property
  def game_events(self):
    """
    The game events in the current tick.
    """
    from .gameevents import create_game_event

    events = []
    for data in self._game_events:
      events.append(create_game_event(stream_binding=self, data=data))
    return events

  # Just another layer of indirection
  # These are properties for autodoc reasons mostly
  @property
  def world(self):
    """
    The Skadi wold object for the current tick.
    """
    return self._stream.world

  @property
  def tick(self):
    """
    The current tick.
    """
    return self._stream.tick

  @property
  def demo(self):
    """
    The Skadi demo object that the binding is reading from.
    """
    return self._demo

  @property
  def modifiers(self):
    """
    The Skadi modifiers object for the tick.
    """
    return self._stream.modifiers

  @property
  def string_tables(self):
    """
    The string_table provided by Skadi.
    """
    return self._stream.string_tables

  @property
  def prologue(self):
    """
    The prologue of the replay.
    """
    return self._stream.prologue

  def __init__(self, demo, start_tick=None, start_time=None):
    self._demo = demo
    self._user_messages = []
    self._game_events = []

    self._state_change_ticks = {
      "start": 0,
      "end": self.demo.file_info.playback_ticks - 2
    }

    self.go_to_tick(self.demo.file_info.playback_ticks - 2)

    self._state_change_times = {
      "draft": self.info.draft_start_time,
      "pregame": self.info.pregame_start_time,
      "game": self.info.game_start_time,
      "postgame": self.info.game_end_time
    }

    # We're already here!
    if start_tick == "end":
      pass
    elif start_tick is not None:
      self.go_to_tick(start_tick)
    elif start_time is not None:
      self.go_to_time(start_time)
    else:
      self.go_to_state_change("game")

  def iter_ticks(self, start=None, end=None, step=1):
    """
    A generator that iterates through the demo's ticks and updates the
    :class:`StreamBinding` to that tick. Yields the current tick.

    The start parameter defines the tick to iterate from, and if not set, the
    current tick will be used instead.

    The end parameter defines the point to stop iterating; if not set,
    the iteration will continue until the end of the replay.

    The step parameter is the number of ticks to consume before yielding
    the tick; the default of one means that every tick will be yielded. Do
    not assume that the step is precise; the gap between two ticks will
    always be larger than the step, but usually not equal to it.
    """
    if start is not None:
      self.go_to_tick(start)

    if end is None:
      end = self._state_change_ticks["end"]

    self._user_messages = []
    self._game_events = []

    last_tick = self.tick - step - 1
    for _ in self._stream:
      if isinstance(end, str):
        if self.info.game_state == end:
          break
      elif self.tick >= end:
        break

      self._user_messages.extend(self._stream.user_messages)
      self._game_events.extend(self._stream.game_events)

      if self.tick - last_tick < step:
        continue
      else:
        last_tick = self.tick

      yield self.tick

      self._user_messages = []
      self._game_events = []

  def go_to_tick(self, tick):
    """
    Moves to the given tick, or the nearest tick after it. Returns the tick
    moved to.
    """
    if isinstance(tick, str):
      return self.go_to_state_change(tick)

    if tick > self.demo.file_info.playback_ticks or tick < 0:
      raise IndexError("Tick {} out of range".format(tick))

    self._stream = self.demo.stream(tick=tick)
    self._user_messages = (self._stream.user_messages or [])[:]
    self._game_events = (self._stream.game_events or [])[:]

    return self.tick

  def go_to_time(self, time):
    """
    Moves to the tick with the given game time. Could potentially overshoot,
    but not by too much. Will not undershoot.

    Returns the tick it has moved to.
    """
    # Go for 31 tps as would rather exit FP loop earlier than
    # sooner. 1.5 for same reason
    FP_REGION = 1800 * 1.5 / 31

    # If the time we're going to is behind us, recreate the stream
    if time < self.info.game_time:
      self._stream = self.demo.stream(tick=0)

    # If the time is more than 1.5 full packets ahead of us, iter full ticks
    if time > self.info.game_time + FP_REGION:
      for _ in self._stream.iterfullticks():
        # If this full tick is within 1.5 full packets of the target, stop
        if self.info.game_time + FP_REGION > time and\
           self.info.game_time < time:
          break
      else:
        # If we didn't stop via break, then it was EOF, so raise
        raise IndexError("Time {} out of range".format(time))

    for _ in self._stream:
      if self.info.game_time > time:
        break
    else:
      raise IndexError("Time {} out of range".format(time))

    self._user_messages = self._stream.user_messages[:]
    self._game_events = self._stream.game_events[:]
    return self.tick

  def go_to_state_change(self, state):
    """
    Moves to the time when the :attr:`GameInfo.game_state` changed to the given
    state. Valid values are equal to the possible values of
    :att:`~GameInfo.game_state`, along with ``"start"`` and ``"end"`` which
    signify the first and last tick in the replay, respectively.

    Returns the tick moved to.
    """
    if state in self._state_change_ticks:
      return self.go_to_tick(self._state_change_ticks[state])
    elif state in self._state_change_times:
      return self.go_to_time(self._state_change_times[state])
    else:
      raise ValueError("Unsupported state {}".format(repr(state)))

  def __iter__(self):
    return self.iter_ticks()

  @property
  def players(self):
    """
    A list of :class:`Player` objects, one for each player in the game.
    This excludes spectators and other non-hero-controlling players.
    """
    from . import Player

    return [p for p in Player.get_all(self) if
            p.index != None and p.team != "spectator"]

  @property
  def info(self):
    """
    The :class:`GameInfo` object for the replay.
    """
    from .gameinfo import GameInfo
    info = GameInfo.get_all(self)
    assert len(info) == 1
    return info[0]

  @property
  def creeps(self):
    """
    The :class:`CreepManager` object for the replay.
    """
    from .creeps import CreepManager

    return CreepManager(self)

  @property
  def buildings(self):
    """
    The :class:`BuildingManager` object for the replay.
    """
    from .buildings import BuildingManager
    return BuildingManager(self)
	
  @staticmethod
  def from_file(filename, *args, **kwargs):
    """
    Loads the demo from the filename, and then initialises the
    :class:`StreamBinding` with it, along with any other passed arguments.
    """
    import skadi.demo

    demo = skadi.demo.construct(filename)

    return StreamBinding(demo, *args, **kwargs)