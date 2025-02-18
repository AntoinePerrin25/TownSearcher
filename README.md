
# Commune Predictor App

This project is a french application for searching and predicting communes (municipalities) in France, Germany, and Switzerland. The application uses a combination of Python, C, and Cython to provide fast and efficient search and correction functionalities.

## Features

- Search for communes by name with different search types (containing, starting with, ending with).
- Display search results with pagination.
- Sort results by name, length, or department code.
- Option to enable correction suggestions based on Levenshtein distance.
- Select which countries' data to include in the search (France, Germany, Switzerland).

## Requirements

- Python 3.6+
- Pandas
- Tkinter
- Cython
- A C compiler (e.g., GCC, MSVC)

## Setup

1. Clone the repository:
    ```sh
    git clone <repository-url>
    cd <repository-directory>
    ```

2. Install the required Python packages:
    ```sh
    pip install pandas cython
    ```

3. Compile the C functions:
    ```sh
    gcc -shared -o functions.dll -fPIC functions.c
    ```

4. Place the compiled `functions.dll` in the same directory as `main.py`.

5. Ensure the CSV files (`Communes_France.csv`, `Communes_Allemagne.csv`, `Communes_Suisse.csv`) are in the same directory as `main.py`.

## Usage

Run the application:
```sh
python main.py
```

## File Structure

- `main.py`: The main Python script containing the GUI and logic.
- `functions.c`: The C file containing the functions for calculating distances and filtering data.
- `functions.dll`: The compiled shared library from `functions.c`.
- `Communes_France.csv`, `Communes_Allemagne.csv`, `Communes_Suisse.csv`: CSV files containing commune data for France, Germany, and Switzerland respectively.

## License

This project is licensed under the MIT License.
