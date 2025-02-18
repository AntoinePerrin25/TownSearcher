# Commune Predictor App

This project is a GUI application for searching and predicting communes using data from France, Germany, and Switzerland. It leverages C functions for efficient data processing.

## Project Structure

Cython
├── communes/ │
              ├── France.csv
              ├── Allemagne.csv
              └── Suisse.csv 
├── src/ │
         ├── functions.c
         └── main.py 
├── shared/functions.dll 
└── README.md

## Setting Up the Project

1. Clone the repository
2. Install the required packages using the following command:
```
pip install -r requirements.txt
```


## Running the Application

To run the application, execute the following command:
```
python src/main.py
```