import sys
import os
import pandas as pd


# To execute it you have to launch in the terminal the following command
# python row_col_invert.py path
#
# The path can be either a file with json or csv extension or a folder.
def swap_element(stack):
    parts = stack.split('.')
    if len(parts) >= 2:
        parts[0], parts[1] = parts[1], parts[0]

    return '.'.join(parts)


def transpose_matrix(matrix):
    return [list(column) for column in zip(*matrix)]


def transform_file(file_name):
    if not os.path.exists(file_name):
        print("The file path didn't exists")
        return
    with open(file_name, 'r') as open_file:
        if file_name.endswith('csv'):
            csv_file = pd.read_csv(open_file, dtype={'Stack': str}, keep_default_na="")
            if 'Stack' in csv_file:
                csv_file['Stack'] = csv_file['Stack'].apply(swap_element)
                csv_file.to_csv(file_name.replace('.csv', '_revert.csv'), index=False)
            else:
                print(f"File {file_name} has not column 'Stack'")

        elif file_name.endswith('json'):
            import json
            json_file = json.load(open_file)
            table = json_file['signal_cfg']['model']['table']
            for line in table:
                line[2] = swap_element(line[2])

            with open(file_name.replace('.json', '_revert.json'), 'w') as file_w:
                json.dump(json_file, file_w, indent=4)
        else:
            print(f"The file {file_name} has not .csv or .json extension")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("You need to pass as argument one file with .csv or .json extension or a folder ")
        sys.exit()

    if os.path.isdir(sys.argv[1]):
        for file in os.listdir(sys.argv[1]):
            if "revert" not in file:
                transform_file(f"{sys.argv[1]}/{file}")
    else:
        transform_file(sys.argv[1])
