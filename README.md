# Data Processing

The output of the enclosure script generates `monitor.log` and `air_data.log` which are both timestamped files containing controller actions and air quality data, respectively. There are two files because the air sensor logs its data from a different process than the controller itself, and multiple log files do not work with multiprocessing by default.

Currently the post-processing script does the following:

  - Parses both log files into python data structures
  - Correlates the data into a timeline
  - Overlays the data on the appropriate image
  - Generates graphs of the data (soon)

The images, once edited with overlay data, are then ready to be made into a time-lapse video.

## Usages

Common args

```
$ python3 process_logs.py --help
usage: process_logs.py [-h] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--json] [--start START] [--end END] {graph,frames} ...

positional arguments:
  {graph,frames}        Post-processor commands
    graph               Generate graphs from air data logs
    frames              Overlay sensor data onto image frames captured by the enclosure service. Source image file locations extracted from monitor log.

optional arguments:
  -h, --help            show this help message and exit
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}, -l {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Log level per python logging module
  --json, -j            Output log data in JSON format to STDOUT and exit.
  --start START, -s START
                        Starting timestamp for graph in format "DD-MM-YYYY HH:MM:SS"
  --end END, -e END     Ending timestamp for graph in format "DD-MM-YYYY HH:MM:SS"
```

Data graphs

```
$ python3 process_logs.py graph --help
usage: process_logs.py graph [-h] [--file FILE] [--data [{rh,co2,temp} ...]]

optional arguments:
  -h, --help            show this help message and exit
  --file FILE, -f FILE  If provided, write the graph image to the provided file location
  --data [{rh,co2,temp} ...], -d [{rh,co2,temp} ...]
                        Which data types to graph. `rh` for relative humidity, `co2` for CO2 levels, `temp` for temperature. To select multiple types, separate by spaces. e.g. `--data rh co2`
```

Image frames

```
$ python3 process_logs.py frames --help
usage: process_logs.py frames [-h] [--clobber] --output-dir OUTPUT_DIR [--nth-frame NTH_FRAME]

optional arguments:
  -h, --help            show this help message and exit
  --clobber, -c         Overwrite existing output images
  --output-dir OUTPUT_DIR, -o OUTPUT_DIR
                        Directory for writing modified images
  --nth-frame NTH_FRAME, -n NTH_FRAME
                        Only overlay and write every Nth image frame. For example, `-n 10` would only write every 10th image to output directory. Uses modulo operator on filename to determine which images to write.
```

# Generating Video

Compile pictures into video

Make sure to change `%03d` in the path argument to match the number of digits in filename

[ffmepg image2](https://ffmpeg.org/ffmpeg-formats.html#image2-1)

```
$ ffmpeg -framerate 24 -i '/media/asustor/MushroomFarm/data/images/image_%03d.jpg' out.mkv
```

Add `-start_number` if you want to skip some of this images

```
$ ffmpeg -framerate 24 -start_number 3986 -i '/media/asustor/MushroomFarm/data/images_final/image_%04d.jpg' ~/out2.mkv
```

Or maybe all images in a directory

```
$ ffmpeg -framerate 24 -pattern_type glob -i '/media/asustor/MushroomFarm/data/img_out_test/*.jpg' out_30072023.mkv
```

And then to concatenate the two videos, pass a file containing a list of filenames

[ffmpeg concat](https://ffmpeg.org/ffmpeg-formats.html#concat-1)

```
$ ffmpeg -f concat -safe 0 -i <(printf "file /home/harry/out.mkv\nfile /home/harry/out2.mkv") -c copy ~/out_final.mkv
```

# TODO

- Add argument parsing to specify config, or maybe just have a config file? Por que no los dos?
