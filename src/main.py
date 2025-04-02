import pandas as pd
import tkinter as tk
from tkinter import ttk
import threading
import ctypes
import os
import platform
import time
from icecream import ic

# Check if we should use CUDA
use_cuda = os.environ.get("USE_CUDA", "0") == "1"

# Load the shared library into ctypes
if platform.system() == "Windows":
    if use_cuda:
        try:
            functions_lib = ctypes.CDLL('./shared/functions_cuda.dll')
            print("Using CUDA acceleration!")
        except OSError:
            functions_lib = ctypes.CDLL('./shared/functions.dll')
            use_cuda = False
            print("Falling back to CPU implementation.")
    else:
        functions_lib = ctypes.CDLL('./shared/functions.dll')
else:  # Unix-like systems
    if use_cuda:
        try:
            functions_lib = ctypes.CDLL('./shared/functions_cuda.so')
            print("Using CUDA acceleration!")
        except OSError:
            functions_lib = ctypes.CDLL('./shared/functions.so')
            use_cuda = False
            print("Falling back to CPU implementation.")
    else:
        functions_lib = ctypes.CDLL('./shared/functions.so')

# CUDA debug information
cuda_info = {
    "enabled": use_cuda,
    "device": "Unknown",
    "last_operation_time": 0,
    "total_operations": 0,
    "avg_operation_time": 0
}

# Try to get CUDA device information if CUDA is enabled
if use_cuda:
    try:
        # Using subprocess to call nvidia-smi
        import subprocess
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            cuda_info["device"] = result.stdout.strip()
        else:
            cuda_info["device"] = "CUDA device information unavailable"
    except Exception as e:
        cuda_info["device"] = f"Error getting CUDA device info: {str(e)}"
    
    print(f"CUDA Device: {cuda_info['device']}")

# Define the argument and return types for the C functions
if use_cuda:
    # CUDA functions
    functions_lib.cuda_calculate_distances.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t, ctypes.c_size_t]
    functions_lib.cuda_calculate_distances.restype = None
    
    functions_lib.cuda_filter_df.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    functions_lib.cuda_filter_df.restype = None
    
    functions_lib.cuda_calculate_final_distances.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)]
    functions_lib.cuda_calculate_final_distances.restype = None
else:
    # CPU functions
    functions_lib.calculate_distances.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_size_t, ctypes.c_size_t]
    functions_lib.calculate_distances.restype = None
    
    functions_lib.filter_df.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
    functions_lib.filter_df.restype = None
    
    functions_lib.calculate_final_distances.argtypes = [ctypes.POINTER(ctypes.c_char_p), ctypes.c_size_t, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)]
    functions_lib.calculate_final_distances.restype = None

class CommunePredictorApp:
    def __init__(self, root):
        self.root = root
        if self.root is not None:
            self.root.title("Recherche de Communes avec Prédiction")
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Charger les données
        self.df_France = self.load_communes_data('./communes/France.csv')
        self.df_Allemange = self.load_communes_data('./communes/Allemagne.csv')
        self.df_Suisse = self.load_communes_data('./communes/Suisse.csv')
        
        # Variables for checkboxes
        self.france_var = tk.BooleanVar(value=True)
        self.allemagne_var = tk.BooleanVar(value=False)
        self.suisse_var = tk.BooleanVar(value=False)
       
        # Variables for pagination
        self.results_per_page = 10
        self.current_page = 0
        self.results = pd.DataFrame(columns = ['Pays', 'nom_standard', 'dep_code'])
        self.sort_order = True
        
        self.correction_var = tk.BooleanVar()
        
        self.min_distance = 15  # Minimum Levenshtein distance to consider
        self.max_suggestions = 20  # Maximum number of suggestions to add
        
        # Event to cancel ongoing calculations
        self.cancel_event = threading.Event()
        
        # Add debug mode variable
        self.debug_var = tk.BooleanVar(value=False)
        
        # Add performance tracking
        self.perf_metrics = {
            "filter_time": 0,
            "distance_calc_time": 0,
            "total_operations": 0
        }
        
        # Interface graphique
        self.create_widgets()
        
        # Initialize the combined dataframe
        self.df = pd.DataFrame(columns=['Pays', 'nom_standard', 'nom_sans_accent', 'nom_standard_majuscule', 'dep_code'])
        
        # Combine the dataframes into one if checkboxes are checked
        self.update_combined_df()
        
        # Show CUDA status
        if use_cuda:
            self.show_cuda_info()

    
    def load_communes_data(self, filepath: str) -> pd.DataFrame:
        # Pays,nom_standard,nom_sans_accent,nom_standard_majuscule,dep_code,nom_standard
        dtype = {
            'Pays': str,
            'nom_standard': str,
            'nom_sans_accent': str,
            'nom_standard_majuscule': str,
            'dep_code': str
        }
        
        df = pd.DataFrame(columns=['Pays', 'nom_standard', 'nom_sans_accent', 'nom_standard_majuscule', 'dep_code'])
        if os.path.exists(filepath):
            read = pd.read_csv(filepath, dtype=dtype)
            df = pd.concat([df, read], ignore_index=True)  # ensure index is reset
        else:
            print(f"File not found: {filepath}")
        return df

    def correction(self, query, min_distance, max_suggestions) -> pd.DataFrame:
        names = self.df['nom_standard'].values
        dep_codes = self.df['dep_code'].values
        pays = self.df['Pays'].values
        names_count = len(names)
        
        # Convert names to ctypes array
        names_ctypes = (ctypes.c_char_p * names_count)(*map(lambda x: x.encode('utf-8'), names))
        distances = (ctypes.c_size_t * names_count)()
        
        # Call the appropriate function (CUDA or CPU) with timing
        start_time = time.time()
        if use_cuda:
            functions_lib.cuda_calculate_final_distances(names_ctypes, names_count, query.encode('utf-8'), distances)
        else:
            functions_lib.calculate_final_distances(names_ctypes, names_count, query.encode('utf-8'), distances)
        elapsed = time.time() - start_time
        
        # Update performance metrics
        self.perf_metrics["distance_calc_time"] = elapsed
        self.perf_metrics["total_operations"] += 1
        
        if use_cuda:
            cuda_info["last_operation_time"] = elapsed
            cuda_info["total_operations"] += 1
            cuda_info["avg_operation_time"] = ((cuda_info["avg_operation_time"] * 
                                             (cuda_info["total_operations"] - 1)) + 
                                             elapsed) / cuda_info["total_operations"]
        
        if self.debug_var.get():
            print(f"Distance calculation completed in {elapsed:.4f} seconds for {names_count} names")
            if use_cuda:
                print(f"CUDA avg operation time: {cuda_info['avg_operation_time']:.4f} seconds")
        
        # Create a list of tuples (distance, pays, name, dep_code)
        distance_items = [(distances[i], pays[i], names[i], dep_codes[i]) for i in range(names_count)]
        
        # Sort by distance and take max_suggestions items with distance < min_distance
        distance_items.sort(key=lambda x: x[0])
        filtered_items = [item for item in distance_items if item[0] < min_distance][:max_suggestions]
        
        # Collect results
        results = [(item[1], item[2], item[3]) for item in filtered_items]
        
        additional_results_df = pd.DataFrame(results, columns=['Pays', 'nom_standard', 'dep_code'])
        return additional_results_df[['Pays', 'nom_standard', 'dep_code']]

    def filter_df(self, query, search_type) -> pd.DataFrame:
        names = self.df['nom_standard'].values
        names_sans_accent = self.df['nom_sans_accent'].values
        names_majuscule = self.df['nom_standard_majuscule'].values
        names_count = len(names)
        
        # Convert names to ctypes array
        
        names_ctypes = (ctypes.c_char_p * names_count)(*map(lambda x: x.encode('utf-8'), names))
        names_sans_accent_ctypes = (ctypes.c_char_p * names_count)(*map(lambda x: x.encode('utf-8'), names_sans_accent))
        names_majuscule_ctypes = (ctypes.c_char_p * names_count)(*map(lambda x: x.encode('utf-8'), names_majuscule))
        results = (ctypes.c_int * names_count)()
        
        # Call the appropriate function (CUDA or CPU) with timing
        start_time = time.time()
        if use_cuda:
            functions_lib.cuda_filter_df(names_ctypes, names_sans_accent_ctypes, names_majuscule_ctypes, names_count, query.encode('utf-8'), search_type.encode('utf-8'), results)
        else:
            functions_lib.filter_df(names_ctypes, names_sans_accent_ctypes, names_majuscule_ctypes, names_count, query.encode('utf-8'), search_type.encode('utf-8'), results)
        elapsed = time.time() - start_time
        
        # Update performance metrics
        self.perf_metrics["filter_time"] = elapsed
        self.perf_metrics["total_operations"] += 1
        
        if use_cuda:
            cuda_info["last_operation_time"] = elapsed
            cuda_info["total_operations"] += 1
            cuda_info["avg_operation_time"] = ((cuda_info["avg_operation_time"] * 
                                             (cuda_info["total_operations"] - 1)) + 
                                             elapsed) / cuda_info["total_operations"]
        
        if self.debug_var.get():
            print(f"Filter operation completed in {elapsed:.4f} seconds for {names_count} names")
            if use_cuda:
                print(f"CUDA avg operation time: {cuda_info['avg_operation_time']:.4f} seconds")
        
        # Collect results
        filtered_indices = [i for i in range(names_count) if results[i] == 1]
        filtered_df = self.df.iloc[filtered_indices]
        
        return filtered_df
    
    def on_key_release(self):
        current_query = self.entry_var.get().strip()
        if current_query != self.previous_query:
            self.previous_query = current_query
            self.current_page = 0
            self.update_suggestions()
        
    def create_widgets(self) -> None:
        # Configure row and column weights to make the scrolling area expand
        self.root.grid_rowconfigure(3, weight=1)  # Make the suggestions row expandable
        self.root.grid_columnconfigure(0, weight=1)
        
        # Row 0
        row = 0
        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(self.root, textvariable=self.entry_var, width=60)
        self.entry.grid(row=row, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
        self.previous_query = ""
        self.entry.bind("<KeyRelease>", lambda event: self.on_key_release())
        
        # Row 1
        row = 1
        options_frame = tk.Frame(self.root)
        options_frame.grid(row=row, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
        
        # Search options in options_frame
        self.search_type_var = tk.StringVar(value="Contenant")
        search_type_menu = ttk.OptionMenu(options_frame, self.search_type_var, "Contenant", 
                                        "Commencant par", "Finissant par", "Contenant", 
                                        command=self.update_suggestions)
        search_type_menu.pack(side=tk.LEFT, padx=10)

        sort_types = ["Nom", "Longueur", "Département", "Distance"]
        self.sort_type_var = tk.StringVar(value="Nom (A-Z)")
        sort_type_menu = ttk.OptionMenu(options_frame, self.sort_type_var, *sort_types, 
                                    command=self.update_suggestions)
        sort_type_menu.pack(side=tk.LEFT, padx=10)

        self.sort_button = tk.Button(options_frame, text="↑", command=self.toggle_sort_order)
        self.sort_button.pack(side=tk.LEFT, padx=5)
        
        # Row 2
        row = 2
        checkboxes_frame = tk.Frame(self.root)
        checkboxes_frame.grid(row=row, column=0, columnspan=4, padx=10, pady=5, sticky="ew")
        
        self.correction_checkbutton = ttk.Checkbutton(checkboxes_frame, text="Correction", 
                                                variable=self.correction_var, 
                                                command=self.update_suggestions)
        self.correction_checkbutton.pack(side=tk.LEFT, padx=10)

        self.france_checkbutton = ttk.Checkbutton(checkboxes_frame, text="France", 
                                            variable=self.france_var, 
                                            command=self.update_combined_df)
        self.france_checkbutton.pack(side=tk.LEFT, padx=10)

        self.allemagne_checkbutton = ttk.Checkbutton(checkboxes_frame, text="Allemagne", 
                                                variable=self.allemagne_var, 
                                                command=self.update_combined_df)
        self.allemagne_checkbutton.pack(side=tk.LEFT, padx=10)

        self.suisse_checkbutton = ttk.Checkbutton(checkboxes_frame, text="Suisse", 
                                            variable=self.suisse_var, 
                                            command=self.update_combined_df)
        self.suisse_checkbutton.pack(side=tk.LEFT, padx=10)
        
        # After the checkboxes for countries, add debug mode checkbox
        tk.Label(checkboxes_frame, text=" | ").pack(side=tk.LEFT)
        
        # Add debug checkbox
        self.debug_checkbutton = ttk.Checkbutton(checkboxes_frame, text="Debug", 
                                              variable=self.debug_var)
        self.debug_checkbutton.pack(side=tk.LEFT, padx=10)
        
        # Add CUDA info button if CUDA is available
        if use_cuda:
            self.cuda_info_button = tk.Button(checkboxes_frame, text="CUDA Info", 
                                           command=self.show_cuda_info)
            self.cuda_info_button.pack(side=tk.LEFT, padx=5)
        
        # Row 3 - Suggestions area (expandable)
        row = 3
        suggestions_frame_container = tk.Frame(self.root)
        suggestions_frame_container.grid(row=row, column=0, columnspan=4, padx=10, pady=5, sticky="nsew")

        canvas = tk.Canvas(suggestions_frame_container)
        scrollbar = ttk.Scrollbar(suggestions_frame_container, orient="vertical", command=canvas.yview)
        self.suggestions_canvas_frame = tk.Frame(canvas)

        self.suggestions_canvas_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        canvas.create_window((0, 0), window=self.suggestions_canvas_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Row 4 - Letters frame
        row = 4
        self.rowletters = row
        self.letter_buttons_frame = tk.Frame(self.root)
        self.letter_buttons_frame.grid(row=row, column=0, columnspan=4, pady=5, sticky="ew")

        # Row 5 - Results count
        row = 5
        self.results_count_label = tk.Label(self.root, text="Page 0/0 Résultats: 0")
        self.results_count_label.grid(row=row, column=0, columnspan=2, pady=5, sticky="w")

        # Row 6 - Pagination
        row = 6
        pagination_frame = tk.Frame(self.root)
        pagination_frame.grid(row=row, column=0, columnspan=4, pady=5, sticky="ew")

        self.prev_page_button = tk.Button(pagination_frame, text="<-", command=self.prev_page)
        self.prev_page_button.pack(side=tk.LEFT, padx=5)

        self.next_page_button = tk.Button(pagination_frame, text="->", command=self.next_page)
        self.next_page_button.pack(side=tk.LEFT, padx=5)

        self.increase_results_button = tk.Button(pagination_frame, text="+", command=self.increase_results_per_page)
        self.increase_results_button.pack(side=tk.LEFT, padx=5)

        self.decrease_results_button = tk.Button(pagination_frame, text="-", command=self.decrease_results_per_page)
        self.decrease_results_button.pack(side=tk.LEFT, padx=5)

        # Set minimum window size
        self.root.update()
        self.root.minsize(width=self.root.winfo_width(), height=400)
        
        # Set initial focus
        self.entry.focus_set()
    
    def search_communes(self, query: str, search_type: str) -> pd.DataFrame:
        filtered_df = self.filter_df(query, search_type)
        if self.correction_var.get():
            additional_results_df = self.correction(query, self.min_distance, self.max_suggestions)
            filtered_df = pd.concat([filtered_df, additional_results_df])
                
        return filtered_df[['Pays', 'nom_standard', 'dep_code']]

    def sort_results(self, results: pd.DataFrame) -> pd.DataFrame:
        sort_type = self.sort_type_var.get()
        if sort_type == "Distance":
            return results.sort_values(by='distance', ascending=self.sort_order)
        elif sort_type == "Nom":
            results = results.sort_values(by='nom_standard', ascending=self.sort_order)
        elif sort_type == "Longueur":
            results = results.assign(length=results['nom_standard'].str.len()).sort_values(by='length', ascending=self.sort_order).drop(columns='length')
        elif sort_type == "Département":
            results = results.sort_values(by='dep_code', ascending=self.sort_order)
        return results

    def update_suggestions(self, event=None) -> None:
        query = self.entry_var.get().strip()
        search_type = self.search_type_var.get()
        self.cancel_event.set()  # Cancel any ongoing calculations
        self.cancel_event = threading.Event()  # Create a new event for the new thread
        threading.Thread(target=self._update_suggestions_thread, args=(query, search_type, self.cancel_event)).start()

    def _update_suggestions_thread(self, query: str, search_type: str, cancel_event: threading.Event) -> None:
        start_time = time.time()
        self.results = self.search_communes(query, search_type)
        if cancel_event.is_set():
            return
        
        # Calculate distances for final results
        names_count = len(self.results)
        if names_count > 0:
            names = self.results['nom_standard'].values
            names_ctypes = (ctypes.c_char_p * names_count)(*map(lambda x: x.encode('utf-8'), names))
            distances = (ctypes.c_size_t * names_count)()
            
            # Call the appropriate function (CUDA or CPU)
            dist_start = time.time()
            if use_cuda:
                functions_lib.cuda_calculate_final_distances(names_ctypes, names_count, query.encode('utf-8'), distances)
            else:
                functions_lib.calculate_final_distances(names_ctypes, names_count, query.encode('utf-8'), distances)
            dist_time = time.time() - dist_start
            
            # Add distances to dataframe
            self.results['distance'] = list(distances)
            
            if self.debug_var.get():
                print(f"Final distance calculation: {dist_time:.4f}s for {names_count} results")
        
        self.results = self.results.drop_duplicates(subset=['nom_standard'])
        self.results = self.sort_results(self.results)
        self.current_page = 0
        
        total_time = time.time() - start_time
        if self.debug_var.get():
            mode = "CUDA" if use_cuda else "CPU"
            print(f"[{mode}] Total suggestion update: {total_time:.4f}s")
            print(f"Filter: {self.perf_metrics['filter_time']:.4f}s, Distance: {self.perf_metrics['distance_calc_time']:.4f}s")
        
        self.root.after(0, lambda: self.display_results(total_time))
    
    def update_combined_df(self) -> None:
        selected_dfs = []
        if self.france_var.get():
            selected_dfs.append(self.df_France)
        if self.allemagne_var.get():
            selected_dfs.append(self.df_Allemange)
        if self.suisse_var.get():
            selected_dfs.append(self.df_Suisse)
        
        if selected_dfs:
            self.df = pd.concat(selected_dfs)
        else:
            self.df = pd.DataFrame(columns=['Pays', 'nom_standard', 'nom_sans_accent', 'nom_standard_majuscule', 'dep_code'])
        
        self.update_suggestions()
    
    def prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.display_results()

    def next_page(self) -> None:
        if (self.current_page + 1) * self.results_per_page < len(self.results):
            self.current_page += 1
            self.display_results()

    def increase_results_per_page(self) -> None:
        self.results_per_page += 5
        self.display_results()

    def decrease_results_per_page(self) -> None:
        if (self.results_per_page > 5):
            self.results_per_page -= 5
            self.display_results()

    def toggle_sort_order(self) -> None:
        if self.sort_order:
            self.sort_order = False
            self.sort_button.config(text="↓")
        else:
            self.sort_order = True
            self.sort_button.config(text="↑")
        self.update_suggestions()
    
    def display_results(self, total_time=None) -> None:
        if self.results.empty:
            self.results_count_label.config(text="Page 0/0 Résultats: 0")
            for widget in self.suggestions_canvas_frame.winfo_children():
                widget.destroy()
            return

        for widget in self.suggestions_canvas_frame.winfo_children():
            widget.destroy()

        start_idx = self.current_page * self.results_per_page
        end_idx = start_idx + self.results_per_page
        for _, row in self.results.iloc[start_idx:end_idx].iterrows():
            name = row['nom_standard']
            depcode = row['dep_code']
            pays = row['Pays']
            distance = row['distance'] if 'distance' in row else ''
            
            row_frame = tk.Frame(self.suggestions_canvas_frame)
            row_frame.pack(fill=tk.X, padx=5, pady=2)

            copy_button = tk.Button(row_frame, text="Copier", command=lambda n=name: self.copy_to_clipboard(n))
            copy_button.pack(side=tk.RIGHT)
            label = tk.Label(row_frame, text=f"({distance})" if distance != '' else " ", anchor='w', width=5)
            label.pack(side=tk.RIGHT)
            label = tk.Label(row_frame, text=" ", anchor='w')
            label.pack(side=tk.LEFT)
            label = tk.Label(row_frame, text=pays, anchor='w', width=9)
            label.pack(side=tk.LEFT)
            label = tk.Label(row_frame, text=depcode, anchor='w', width=3)
            label.pack(side=tk.LEFT)
            label = tk.Label(row_frame, text=name, anchor='w', width=25)
            label.pack(side=tk.LEFT)

        total_pages = (len(self.results) + self.results_per_page - 1) // self.results_per_page
        self.results_count_label.config(text=f"Page {self.current_page+1}/{total_pages} Résultats: {len(self.results)}")

        self.update_next_letters(self.entry_var.get().strip())
        
        # Display performance info if debug is enabled and we have timing info
        if self.debug_var.get() and total_time is not None:
            # Add performance info at the top
            perf_frame = tk.Frame(self.suggestions_canvas_frame, bg="#f0f0f0")
            perf_frame.pack(fill=tk.X, padx=5, pady=5)
            
            mode = "CUDA" if use_cuda else "CPU"
            perf_label = tk.Label(
                perf_frame, 
                text=f"[{mode}] Process time: {total_time:.4f}s | "
                     f"Filter: {self.perf_metrics['filter_time']:.4f}s | "
                     f"Distance calc: {self.perf_metrics['distance_calc_time']:.4f}s",
                bg="#f0f0f0", fg="#333333"
            )
            perf_label.pack(fill=tk.X)
            
            if use_cuda:
                cuda_label = tk.Label(
                    perf_frame,
                    text=f"CUDA avg time: {cuda_info['avg_operation_time']:.4f}s | "
                         f"Total ops: {cuda_info['total_operations']}",
                    bg="#f0f0f0", fg="#333333"
                )
                cuda_label.pack(fill=tk.X)

    def copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def update_next_letters(self, query: str) -> None:
        self.letter_buttons_frame.destroy()
        self.letter_buttons_frame = tk.Frame(self.root)
        self.letter_buttons_frame.grid(row=self.rowletters, column=0, columnspan=2, pady=5)

        if not query:
            return

        # Extraire les prochaines lettres possibles
        possible_letters = set()
        for name in self.df['nom_standard'].dropna():
            if name.lower().startswith(query.lower()):
                if len(name) > len(query):
                    possible_letters.add(name[len(query)].lower())

        # Créer des boutons pour chaque lettre possible
        for letter in sorted(possible_letters):
            button = tk.Button(self.letter_buttons_frame, text=letter.upper(), command=lambda l=letter: self.append_letter(l))
            button.pack(side=tk.LEFT, padx=2)

    def append_letter(self, letter: str) -> None:
        current_text = self.entry_var.get()
        self.entry_var.set(current_text + letter)
        self.entry.icursor(len(current_text) + 1)
        self.update_suggestions()
    
    def on_closing(self):
        self.cancel_event.set()
        self.root.destroy()

    def show_cuda_info(self):
        """Display CUDA information in a popup window"""
        info_window = tk.Toplevel(self.root)
        info_window.title("CUDA Information")
        info_window.geometry("600x400")
        
        # Add text widget with scrollbar
        text_frame = tk.Frame(info_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set)
        text_widget.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        # Insert CUDA information
        text_widget.insert(tk.END, f"CUDA Acceleration: {'Enabled' if use_cuda else 'Disabled'}\n\n")
        text_widget.insert(tk.END, f"Device Information:\n{cuda_info['device']}\n\n")
        text_widget.insert(tk.END, "Performance will be displayed in real-time when debug mode is enabled.\n")
        
        # Make the text widget read-only
        text_widget.config(state=tk.DISABLED)
        
        # Add a button to close the window
        close_button = tk.Button(info_window, text="Close", command=info_window.destroy)
        close_button.pack(pady=10)


#def main():
if __name__ == "__main__":
    root = tk.Tk()
    app = CommunePredictorApp(root)
    root.mainloop()