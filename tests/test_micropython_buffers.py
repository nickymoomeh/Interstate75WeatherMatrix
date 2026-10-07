"""Exercise import-time sprite compilation with MicroPython's buffer restriction."""
from pathlib import Path


class BufferOnlyBytearray(bytearray):
    def extend(self, value):
        # MicroPython's bytearray.extend accepts buffer objects, not tuples/lists.
        memoryview(value)
        return super().extend(value)


source = Path(__file__).resolve().parents[1].joinpath('ambient_motion.py').read_text()
namespace = {'bytearray': BufferOnlyBytearray}
exec(compile(source, 'ambient_motion.py', 'exec'), namespace)
ordinary = {}
exec(compile(source, 'ambient_motion.py', 'exec'), ordinary)
assert namespace['AIR_SPRITES'] == ordinary['AIR_SPRITES']
assert sum(len(sprite[2]) for sprite in namespace['AIR_SPRITES']) == 128
# Reproduce the exact old failure to ensure this check would have caught it.
original = source.replace('''runs.append(colour - 1)
                runs.append(y)
                runs.append(left)
                runs.append(x - left)''', 'runs.extend((colour - 1, y, left, x - left))')
try:
    exec(compile(original, 'old_ambient_motion.py', 'exec'), {'bytearray': BufferOnlyBytearray})
except TypeError:
    pass
else:
    raise AssertionError('Old import-time tuple extension should fail')
print('MicroPython buffer-restricted import passes; original failure reproduced; sprites unchanged')
