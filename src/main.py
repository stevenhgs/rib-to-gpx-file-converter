from datetime import datetime, timezone
from typing import BinaryIO
from pathlib import Path


def get_raw_track_points(file: BinaryIO, mode: int) -> list[list[int]]:
    """
    This method assumes the given file is a .rib file of goggles of Recon Instruments.
    This method will first put the data of the file in a bytearray.
    This method will then split the bytes in the bytearray into track points.
    This method assumes mode is either 1 or 2.
    Mode 1: track points start from the 14th index and are each 32 bytes long.
    Mode 2: track points start from the 9th index and are each 20 bytes long.
    """
    byte_array = bytearray(file.read())

    if mode == 1:
        start_index = 14
        bytes_per_track_point = 32
        padding = []
    else:  # mode 2
        start_index = 9
        bytes_per_track_point = 20
        # for devices in mode 2 the unix timestamp is not included in the data of every track point
        # the date is only included in the first data slice, so extract it and add it to all the raw_track_points
        year = 2000 + (byte_array[start_index] & 0x7f)
        month = byte_array[start_index + 1]
        day = byte_array[start_index + 2]
        dt = datetime(year, month, day)
        unix_time = int(dt.replace(tzinfo=timezone.utc).timestamp())
        padding = [0, 0, 0, 0]  # padding is added to mode 2 for missing values
        padding_size = len(padding)
        # put the unix timestamp in the 4 bytes of the padding
        for i in range(4):
            padding[padding_size - i - 1] = unix_time % 256
            unix_time //= 256

    base_index = start_index
    raw_track_points = []
    while base_index + bytes_per_track_point <= len(byte_array):
        raw_track_points.append(padding + [byte_array[base_index + i] for i in range(bytes_per_track_point)])
        base_index += bytes_per_track_point
    return raw_track_points


def get_coordinate_from_four_bytes(values: tuple[int, int, int, int]) -> float:
    """
    The given values is a tuple of 4 integer values.
    These integer values come from an unsigned byte, so the integer values should be between 0 and 255.
    This method converts these 4 values to a coordinate and returns the coordinate.
    This coordinate is in DegDec format.
    """
    # 0x7f is 0111 1111 in binary
    # it is assumed that the sign of the coordinate is determined by the most significant bit of the 2nd value,
    # so to get the true value of the 2nd value we mask its 7 least significant bits.
    minutes = (values[1] & 0x7f) * 10000
    minutes += (values[2] & 0x7f) * 100
    minutes += (values[3] & 0x7f)
    coordinate = values[0] + (minutes / (60 * 10000))
    # 0x80 is 1000 0000 in binary
    # to get the sign of the coordinate we mask the most significant bit of the second value
    if (values[1] & 0x80) != 0:
        return -coordinate
    return coordinate


def get_datetime_from_four_bytes(values: tuple[int, int, int, int]) -> datetime:
    """
    The given values is a tuple of 4 integer values.
    These integer values come from an unsigned byte, so the integer values should be between 0 and 255.
    This method converts these 4 values to a datetime and returns this datetime.
    """
    timestamp = values[0] * 256 * 256 * 256
    timestamp += values[1] * 256 * 256
    timestamp += values[2] * 256
    timestamp += values[3]
    return datetime.fromtimestamp(timestamp)


def get_track_points_from_raw_track_points(raw_track_points: list[list[int]]) -> list[dict]:
    """
    This method converts a list of raw track points into a list of track points and returns this list of track points.
    A raw track point is a list of 24 or 32 integer values with each integer value between 0 and 255.
    A track point is a dictionary with the following (key, value type) pairs:
    ('hour', int), ('minute', int), ('second', int), ('latitude', float), ('longitude', float), ('speed', float),
    ('elevation', int), ('year', int), ('month', int), ('day', int), ('temperature', int).
    """
    track_points = []
    for raw_track_point in raw_track_points:
        data = dict()

        # get time
        data['hour'] = raw_track_point[4]
        data['minute'] = raw_track_point[5]
        data['second'] = raw_track_point[6]

        # get coordinates
        latitude_values = (raw_track_point[7], raw_track_point[8], raw_track_point[9], raw_track_point[10])
        longitude_values = (raw_track_point[11], raw_track_point[12], raw_track_point[13], raw_track_point[14])
        data['latitude'] = get_coordinate_from_four_bytes(latitude_values)
        data['longitude'] = get_coordinate_from_four_bytes(longitude_values)

        # get elevation
        data['elevation'] = (raw_track_point[17] * 256) + raw_track_point[18]

        # get speed (in meters per second)
        data['speed'] = (((raw_track_point[15] * 256) + raw_track_point[16]) / 10) * (1000 / 3600)

        # get year, month and day
        unix_time_values = (raw_track_point[0], raw_track_point[1], raw_track_point[2], raw_track_point[3])
        date_time = get_datetime_from_four_bytes(unix_time_values)
        data['year'] = date_time.year
        data['month'] = date_time.month
        data['day'] = date_time.day

        # get temperature
        data['temperature'] = raw_track_point[21] - 40

        track_points += [data]
    return track_points


def generate_gpx_text(track_points: list[dict]) -> str:
    """
    This method creates a gpx text from the given list of track points and returns this gpx text.
    A track point is a dictionary with the following (key, value type) pairs:
    ('hour', int), ('minute', int), ('second', int), ('latitude', float), ('longitude', float), ('speed', float),
    ('elevation', int), ('year', int), ('month', int), ('day', int), ('temperature', int).
    First a header is created and added to the gpx text.
    Then for every track point in track_points a <trkpt> tag is added to the gpx text.
    At the end a footer is added to the gpx text.
    """
    # add header
    gpx_text = '<?xml version="1.0" encoding="UTF-8"?>\n' \
               '<gpx creator="https://github.com/stevenhgs/rib-to-gpx-file-converter" version="1.1" \n' \
               'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/11.xsd" \n' \
               'xmlns:ns3="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" \n' \
               'xmlns="http://www.topografix.com/GPX/1/1" \n' \
               'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ns2="http://www.garmin.com/xmlschemas/GpxExtensions/v3"> \n' \
               '<trk><name>Example gpx</name>\n' \
               '<trkseg>\n'

    # add track points
    for track_point in track_points:
        latitude = str(track_point['latitude'])
        longitude = str(track_point['longitude'])
        elevation = str(track_point['elevation'])
        hour = str(track_point['hour'])
        minute = str(track_point['minute'])
        second = str(track_point['second'])
        speed = str(track_point['speed'])
        year = str(track_point['year'])
        month = str(track_point['month'])
        day = str(track_point['day'])
        temperature = str(track_point['temperature'])

        track_point_text = f'\t<trkpt lat="{latitude}" lon="{longitude}">\n' \
                           f'\t\t<ele>{elevation}</ele>\n' \
                           f'\t\t<time>{year:0>2}-{month:0>2}-{day:0>2}T{hour:0>2}:{minute:0>2}:{second:0>2}Z</time>\n' \
                           f'\t\t<speed>{speed}</speed>\n' \
                           f'\t\t<extensions>\n' \
                           f'\t\t\t<ns3:TrackPointExtension>\n' \
                           f'\t\t\t\t<ns3:atemp>{temperature}.0</ns3:atemp>\n' \
                           f'\t\t\t</ns3:TrackPointExtension>\n' \
                           f'\t\t</extensions>\n' \
                           f'\t</trkpt>\n'

        gpx_text += track_point_text

    # add footer
    gpx_text += '</trkseg>\n' \
                '</trk>\n' \
                '</gpx>'
    return gpx_text


def convert_rib_to_gpx_file(input_file_path_string: str | None, mode_string: str | None, output_file_path_string: str | None = None) -> None:
    """
    This method assumes the given input_file is a .rib file of the snow2 goggles of Recon Instruments.
    This method will the convert the given input_file into a .gpx file with an output_file_name if it is given.
    Otherwise, the name of the .rib file will be given to the generated .gpx file.
    """
    if input_file_path_string is None:
        print('Please provide an input file path.')
        return
    if (mode_string is None) or (not mode_string.isdigit()) or (mode_string != '1' and mode_string != '2'):
        print('Please provide a mode.')
        print('The mode should be either 1 or 2.')
        print('Known modes: ')
        print('Mode 1: Snow2 goggles')
        print('Mode 2: Zeal Optics Transcend')
        return

    mode = int(mode_string)
    input_file_path = Path(input_file_path_string)
    with open(input_file_path, 'rb') as input_file:
        print(f'getting raw track points in mode {mode} ...')
        raw_track_points = get_raw_track_points(input_file, mode)
        if len(raw_track_points) < 2:
            print('File did not contain any track points.')
            return
    raw_track_points.pop(0)  # first track point seems off
    print('getting track points from raw track points ...')
    track_points = get_track_points_from_raw_track_points(raw_track_points)
    print('generating gpx data ...')
    gpx_text = generate_gpx_text(track_points)
    print('creating output file ...')
    if output_file_path_string is None:
        print('no output file given, creating self generated output file name ...')
        # take the input file name and remove the .rib
        input_file_name = input_file_path.name.split('.')[0]
        output_file_path = input_file_path.parent / (input_file_name + '.gpx')
    else:
        print('checking if given output path exists ...')
        output_file_path = Path(output_file_path_string)
        output_subdirectory_path = output_file_path.parent
        if not output_subdirectory_path.is_dir():
            print('given output path does not exist, so creating it ...')
            output_subdirectory_path.mkdir()
    output_file = open(output_file_path, 'w+')
    print('writing gpx data to output file ...')
    output_file.write(gpx_text)
    print('Done.')


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser('rib_to_gpx_converter')
    parser.add_argument('--in', help='The input file path', type=str)
    parser.add_argument('--out', help='The output file path', type=str)
    parser.add_argument('--mode', help='Mode to parse the .rib file', type=str)
    args = vars(parser.parse_args())
    convert_rib_to_gpx_file(args['in'], args['mode'], args['out'])
