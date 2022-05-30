from src.main import convert_rib_to_gpx_file
"""
If you do not want to use the .rib to .gpx file converter for the snow2 goggles of Recon Instruments through a terminal 
this file can be used.
"""


# ONLY change the values of these 2 variables
# make sure to give the output_file_path_string a .gpx at the end
# for example: output_file_path_string = '../output/out.gpx'
input_file_path_string = '../example/DAY90.rib'
output_file_path_string = None
# mode_string should be either '1' or '2' depending on what goggles were used to track the activity
mode_string = '1'


# DO NOT CHANGE THIS CODE
if __name__ == "__main__":
    convert_rib_to_gpx_file(input_file_path_string, mode_string, output_file_path_string)
