import os
import sys
import json
import logging
import argparse
import datetime

from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE_PATH = os.path.abspath('/media/asustor/MushroomFarm')
AIR_DATA = os.path.join(BASE_PATH, 'data', 'air_data.log')
MON_LOG = os.path.join(BASE_PATH, 'data', 'monitor.log')
IMAGES_OUT = os.path.abspath('/media/asustor/MushroomFarm/data/images_final')
IMAGES_OUT_TEST = os.path.abspath('/media/asustor/MushroomFarm/data/images_final_test')


def parse_air_data(start=None, end=None):

    with open(AIR_DATA, 'r') as f:
        file_data = f.read()

    log_lines = file_data.split('\n')

    log_dicts = []

    # 22 Jul 2023 14:06:20 CO2: 1281.21ppm, temp: 23.73°C, rh: 98.36%
    for raw_line in log_lines:

        if not raw_line:
            continue

        # Maybe we could just write a regex...
        line_data = raw_line.split(' ')
        date_str = ' '.join(line_data[:4])
        date_obj = datetime.datetime.strptime(date_str, '%d %b %Y %H:%M:%S')

        if start is not None and date_obj < start:
            continue

        if end is not None and date_obj > end:
            continue

        air_raw = ' '.join(line_data[4:])
        air_parts = air_raw.split(',')
        co2_value = air_parts[0].split(': ')[1].rstrip('ppm')
        temp_value = air_parts[1].split(': ')[1].rstrip('°C')
        rh_value = air_parts[2].split(': ')[1].rstrip('%')

        out = {
                'timestamp': date_obj,
                'co2_ppm': co2_value,
                'temp_degC': temp_value,
                'rh_pct': rh_value,
                }

        log_dicts.append(out)

    log_dicts.sort(key=lambda x: x['timestamp'])

    return log_dicts


def parse_monitor_log(start=None, end=None):

    # 22-Jul-2023 03:05:41.141 [INFO] Capturing /media/asustor/MushroomFarm/data/images/image_10.jpg
    # 22-Jul-2023 03:05:43.182 [INFO] CO2 is HIGH (1528.5 >= 1000), turning ON  OUTLET 6 (fan)
    # 22-Jul-2023 03:05:43.183 [INFO] Setting register bits to 00000010
    # 22-Jul-2023 03:05:57.989 [INFO] HUM is LOW  (94.8 <= 95), turning ON  outlet 7 (humidifier)
    # 22-Jul-2023 03:05:57.990 [INFO] Setting register bits to 00000011
    # 22-Jul-2023 03:06:43.638 [INFO] Capturing /media/asustor/MushroomFarm/data/images/image_11.jpg

    images = []
    states = []

    with open(MON_LOG, 'r') as f:
        file_data = f.read()

    log_lines = file_data.split('\n')

    for raw_line in log_lines:

        if not raw_line:
            continue

        line_data = raw_line.replace('  ', ' ').split(' ')

        date_str = ' '.join(line_data[0:2])
        date_obj = datetime.datetime.strptime(date_str, '%d-%b-%Y %H:%M:%S.%f')

        if start is not None and date_obj < start:
            continue

        if end is not None and date_obj > end:
            continue

        if line_data[3] == 'Capturing':
            image = {'timestamp': date_obj, 'file_path': line_data[4]}
            images.append(image)

        elif len(line_data) >= 9 and 'is' in line_data and 'turning' in line_data:

            # Fix bug in log data
            if 'NIGHT' in line_data and 'ON' in line_data:
                idx = line_data.index('ON')
                line_data[idx] = 'OFF'

            state = {
                    'timestamp': date_obj,
                    'measure': line_data[3],
                    'state': 'ON' in line_data,
                    'device': line_data[-1].strip('()'),
                    }
            states.append(state)

    images.sort(key=lambda x: x['timestamp'])
    states.sort(key=lambda x: x['timestamp'])

    return images, states


def fix_image_paths(images):
    """When images are written to disk, we don't know how many images there will be, so the image name cans
       only have one digit. When the numbers of digits increases, the script creating the images renames all
       the files to match the current digits. As a result, the logs have image filenames that are incorrect,
       as it's unreasonable to edit a log file (is it?). This function fixes the names to match the files
       that actually exist.
    """

    zlen = len(str(len(images)))

    for idx, img in enumerate(images):

        fp = os.path.abspath(img['file_path'])
        dirn, filen = os.path.split(fp)

        img_num = filen.split('_')[1].split('.')[0].zfill(zlen)
        new_fn = os.path.join(dirn, f'image_{img_num}.jpg')

        images[idx]['file_path'] = new_fn

    return images


def correlate_events(images, states, air_data):
    """Find the state of each outlet and the air data points at the time the image was taken
    """

    correlate = []

    all_data = images + states + air_data
    all_data.sort(key=lambda x: x['timestamp'])

    hum_out = False
    heat_out = False
    fan_out = False
    light_out = False

    rh_val = None
    temp_val = None
    co2_val = None

    for row in all_data:

        if 'file_path' in row:
            frame = {
                    'timestamp': row['timestamp'],
                    'file_path': row['file_path'],
                    'hum_outlet': hum_out,
                    'heat_outlet': heat_out,
                    'fan_outlet': fan_out,
                    'light_outlet': light_out,
                    'rh_value': rh_val,
                    'temp_value': temp_val,
                    'co2_value': co2_val,
                    }
            correlate.append(frame)

        elif 'measure' in row:

            if row['device'] == 'fan':
                fan_out = row['state']
            if row['device'] == 'humidifier':
                hum_out = row['state']
            if row['device'] == 'lights':
                light_out = row['state']
            if row['device'] == 'heater':
                heat_out = row['state']

        else:
            rh_val = row['rh_pct']
            temp_val = row['temp_degC']
            co2_val = row['co2_ppm']

    return correlate


def image_overlay(data, target, overwrite=False, mod_frame=1):

    fn = os.path.split(data['file_path'])[1]
    f_target = os.path.join(target, fn)

    if int(fn.split('.')[0].split('_')[1]) % mod_frame > 0:
        return

    if overwrite is False and os.path.isfile(f_target):
        return

    FONT_FILE = os.path.abspath('/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono-Bold.ttf')

    FILL_ON = 'green'
    FILL_OFF = 'red'

    H_MARGIN = 30
    V_MARGIN = 10
    LINE_SP = 90

    FONT_PX = 84
    FONT_RGB = (255, 255, 255)

    img = Image.open(data['file_path'])
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_FILE, FONT_PX)

    date_str = data['timestamp'].strftime('%d-%b-%Y %H:%M').upper()

    draw.text((H_MARGIN, V_MARGIN), date_str, FONT_RGB, font=font)
    draw.text((H_MARGIN, V_MARGIN + LINE_SP), f'HUM: {data["rh_value"]}%', FONT_RGB, font=font)
    draw.text((H_MARGIN, V_MARGIN + LINE_SP * 2), f'CO2: {data["co2_value"]}ppm', FONT_RGB, font=font)
    draw.text((H_MARGIN, V_MARGIN + LINE_SP * 3), f'TMP: {data["temp_value"]}°C', FONT_RGB, font=font)

    # IMG_HSIZE - H_MARGIN - CIRCLE - TEXT_SIZE
    text_str = 'HUMIDIFIER:  '
    h_offset = img.size[0] - H_MARGIN - font.getlength(text_str)
    draw.text((h_offset, 10), text_str, FONT_RGB, font=font)

    fill_color = FILL_ON if data['hum_outlet'] else FILL_OFF
    circle_coords = (img.size[0] - H_MARGIN - FONT_PX, V_MARGIN, img.size[0] - H_MARGIN, V_MARGIN + FONT_PX)
    draw.ellipse(circle_coords, fill=fill_color, outline='black' )

    text_str = 'FAE_FAN:  '
    h_offset = img.size[0] - H_MARGIN - font.getlength(text_str)
    draw.text((h_offset, 100), text_str, FONT_RGB, font=font)

    fill_color = FILL_ON if data['fan_outlet'] else FILL_OFF
    circle_coords = (img.size[0] - H_MARGIN - FONT_PX, V_MARGIN + LINE_SP, img.size[0] - H_MARGIN, V_MARGIN + FONT_PX + LINE_SP)
    draw.ellipse(circle_coords, fill=fill_color, outline='black' )

    text_str = 'HEATER:  '
    h_offset = img.size[0] - H_MARGIN - font.getlength(text_str)
    draw.text((h_offset, 190), text_str, FONT_RGB, font=font)

    fill_color = FILL_ON if data['heat_outlet'] else FILL_OFF
    circle_coords = (img.size[0] - H_MARGIN - FONT_PX, V_MARGIN + LINE_SP * 2, img.size[0] - H_MARGIN, V_MARGIN + FONT_PX + LINE_SP * 2)
    draw.ellipse(circle_coords, fill=fill_color, outline='black' )

    text_str = 'LIGHTS:  '
    h_offset = img.size[0] - H_MARGIN - font.getlength(text_str)
    draw.text((h_offset, 280), text_str, FONT_RGB, font=font)

    fill_color = FILL_ON if data['light_outlet'] else FILL_OFF
    circle_coords = (img.size[0] - H_MARGIN - FONT_PX, V_MARGIN + LINE_SP * 3, img.size[0] - H_MARGIN, V_MARGIN + FONT_PX + LINE_SP * 3)
    draw.ellipse(circle_coords, fill=fill_color, outline='black' )

    logging.info(f'Writing image {f_target}')
    img.save(f_target, quality='keep')


def generate_graphs(air_data, points=['co2', 'rh', 'temp'], start=None, end=None, outfile=None):

    ts = []
    co2 = []
    rh = []
    temp = []

    for idx, row in enumerate(air_data):

        if start is not None and row['timestamp'] < start:
            continue

        if end is not None and row['timestamp'] > end:
            continue

        ts.append(row['timestamp'])

        if 'co2' in points:
            co2.append(float(row['co2_ppm']))

        if 'rh' in points:
            rh.append(float(row['rh_pct']))

        if 'temp' in points:
            temp.append(float(row['temp_degC']))

    gconf = {
            'co2': {'color': 'r', 'ylabel': 'CO2 (ppm)', 'data': co2},
            'rh': {'color': 'b', 'ylabel': 'Humidity (%)', 'data': rh},
            'temp': {'color': 'g', 'ylabel': 'Temp (°C)', 'data': temp},
            }

    fig, ax = plt.subplots(nrows=len(points), sharex=True)
    fig.suptitle('Enclosure Air Data')

    for idx, point in enumerate(points):
        ax[idx].plot(ts, gconf[point]['data'], gconf[point]['color'])
        ax[idx].set_ylabel(gconf[point]['ylabel'])
        ax[idx].grid(True)

        if idx == 0:
            ax[idx].xaxis.set_major_locator(mdates.DayLocator(interval=1))
            ax[idx].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax[idx].xaxis.set_minor_locator(mdates.HourLocator(interval=6))

    fig.autofmt_xdate()
    plt.xticks(rotation=45, ha='right')

    if outfile is None:
        plt.show()
    else:
        outfile = os.path.abspath(outfile)
        fig.savefig(outfile)
        logging.info(f'Wrote figure image to {outfile}')
        plt.close(fig)


def parse_args():

    root = argparse.ArgumentParser(prog='process_logs.py')
    root.add_argument('--log-level', '-l', action='store', help='Log level per python logging module', default='INFO', choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'], required=False)
    root.add_argument('--json', '-j', action='store_true', help='Output log data in JSON format to STDOUT and exit.', required=False)
    root.add_argument('--start', '-s', action='store', type=lambda d: datetime.datetime.strptime(d, '%d-%m-%Y %H:%M:%S'), required=False, help='Starting timestamp for graph in format "DD-MM-YYYY HH:MM:SS"')
    root.add_argument('--end', '-e', action='store', type=lambda d: datetime.datetime.strptime(d, '%d-%m-%Y %H:%M:%S'), required=False, help='Ending timestamp for graph in format "DD-MM-YYYY HH:MM:SS"')

    children = root.add_subparsers(dest='action', help='Post-processor commands')

    grapher = children.add_parser('graph', help='Generate graphs from air data logs')
    grapher.add_argument('--file', '-f', action='store', required=False, help='If provided, write the graph image to the provided file location')
    grapher.add_argument('--data', '-d', action='store', choices=['rh', 'co2', 'temp'], default=['rh', 'co2', 'temp'], nargs='*', required=False, help='Which data types to graph. `rh` for relative humidity, `co2` for CO2 levels, `temp` for temperature. To select multiple types, separate by spaces. e.g. `--data rh co2`')

    frames = children.add_parser('frames', help='Overlay sensor data onto image frames captured by the enclosure service. Source image file locations extracted from monitor log.')
    frames.add_argument('--clobber', '-c', action='store_true', default=False, required=False, help='Overwrite existing output images')
    frames.add_argument('--output-dir', '-o', action='store', required=True, help='Directory for writing modified images')
    frames.add_argument('--nth-frame', '-n', action='store', type=int, default=1, required=False, help='Only overlay and write every Nth image frame. For example, `-n 10` would only write every 10th image to output directory. Uses modulo operator on filename to determine which images to write.')

    args = root.parse_args()

    if not (args.json or args.action):
        root.print_help()
        sys.exit(1)

    return args


if __name__ == '__main__':

    args = parse_args()

    log_level = getattr(logging, args.log_level)
    logging.basicConfig(level=log_level, format='%(asctime)s [%(levelname)s] %(message)s')

    air_logs = parse_air_data(start=args.start, end=args.end)
    img_data, act_data = parse_monitor_log(start=args.start, end=args.end)
    img_data_fix = fix_image_paths(img_data)

    correlated = correlate_events(img_data_fix, act_data, air_logs)

    if args.json:
        jout = {
                'air_data': air_logs,
                'actions': act_data,
                'images': img_data_fix,
                'correlated': correlated
                }

        print(json.dumps(jout, indent=2, default=str))

    elif args.action == 'graph':
        generate_graphs(air_logs, points=args.data, outfile=args.file)

    elif args.action == 'frames':

        for row in correlated:
            image_overlay(data=row, target=args.output_dir, overwrite=args.clobber, mod_frame=args.nth_frame)

    else:
        print('No command specified')

