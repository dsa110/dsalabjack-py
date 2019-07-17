# Encoder operates +/- 90 deg with output 0.5 - 4.5 V
#
SCALE_FACTOR = 45.0
OFFSET = -22.5

def convert_encoder(voltage):
    return SCALE_FACTOR * voltage + OFFSET