import os
import csv
import sys

"""
The script is used as follows 
python csv_to_semicolon_separator.py <path>
where <path> is the path of the csv folder path with the files to be converted
"""


def convert_csv(input_path, output_path):
    # Create the output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)

    # List all CSV files in the input path
    csv_files = [file for file in os.listdir(input_path) if file.endswith(".csv")]

    if not csv_files:
        print("No CSV files found in the provided path.")
        sys.exit(1)

    for csv_file in csv_files:
        input_file_path = os.path.join(input_path, csv_file)
        output_file_path = os.path.join(output_path, f"{os.path.splitext(csv_file)[0]}.scsv")

        # Check if the CSV file already uses ';' as a separator
        with open(input_file_path, 'r', encoding='utf-8') as input_file:
            first_line = input_file.readline()
            if ';' in first_line:
                print(f"File already uses ';' as separator: {input_file_path}")
                continue

        with open(input_file_path, newline='', encoding='utf-8') as input_file, \
                open(output_file_path, 'w', newline='', encoding='utf-8') as output_file:

            csv_reader = csv.reader(input_file)
            csv_writer = csv.writer(output_file, delimiter=';')

            for row in csv_reader:
                csv_writer.writerow(row)

        print(f"File converted: {output_file_path}")

    print(f"Conversion completed. CSV files converted to SCSV in {output_path}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python csv_to_semicolon_separator.py <path>")
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = os.path.join(in_path, "../scsv")

    convert_csv(in_path, out_path)
