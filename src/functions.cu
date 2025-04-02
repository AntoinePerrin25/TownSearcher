#include <cuda_runtime.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>

// CUDA kernel for calculating Levenshtein distances in parallel
__global__ void levenshtein_kernel(const char* d_strings, const size_t* d_lengths, 
                                 const size_t* d_offsets, const char* d_query, 
                                 size_t query_length, size_t* d_results, size_t strings_count) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= strings_count) return;
    
    // Get string from array using offset
    const char* str = &d_strings[d_offsets[idx]];
    size_t str_length = d_lengths[idx];
    
    // Handle base cases
    if (query_length == 0) {
        d_results[idx] = str_length;
        return;
    }
    if (str_length == 0) {
        d_results[idx] = query_length;
        return;
    }
    
    // Allocate cache in local memory
    size_t* cache;
    cache = new size_t[str_length];
    
    // Initialize cache
    for (size_t i = 0; i < str_length; i++) {
        cache[i] = i + 1;
    }
    
    // Compute Levenshtein distance
    size_t distance, bDistance, result;
    for (size_t bIndex = 0; bIndex < query_length; bIndex++) {
        char code = d_query[bIndex];
        result = distance = bIndex;
        
        for (size_t index = 0; index < str_length; index++) {
            bDistance = code == str[index] ? distance : distance + 1;
            distance = cache[index];
            
            cache[index] = result = distance > result
                ? bDistance > result ? result + 1 : bDistance
                : bDistance > distance ? distance + 1 : bDistance;
        }
    }
    
    d_results[idx] = result;
    delete[] cache;
}

// CUDA kernel for filtering strings based on search criteria
__global__ void filter_kernel(const char* d_strings, const char* d_strings_sans_accent, 
                            const char* d_strings_majuscule, const size_t* d_lengths, 
                            const size_t* d_offsets, const char* d_query, size_t query_length, 
                            int search_type, int* d_results, size_t strings_count) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= strings_count) return;
    
    // Get strings using offsets
    const char* str = &d_strings[d_offsets[idx]];
    const char* str_sans_accent = &d_strings_sans_accent[d_offsets[idx]];
    const char* str_majuscule = &d_strings_majuscule[d_offsets[idx]];
    size_t str_length = d_lengths[idx];
    
    bool match = false;
    
    if (search_type == 0) { // "Commencant par"
        if (str_length >= query_length) {
            bool match_standard = true;
            bool match_sans_accent = true;
            bool match_majuscule = true;
            
            for (size_t i = 0; i < query_length; i++) {
                if (str[i] != d_query[i]) match_standard = false;
                if (str_sans_accent[i] != d_query[i]) match_sans_accent = false;
                if (str_majuscule[i] != d_query[i]) match_majuscule = false;
            }
            
            match = match_standard || match_sans_accent || match_majuscule;
        }
    } 
    else if (search_type == 1) { // "Finissant par"
        if (str_length >= query_length) {
            size_t offset = str_length - query_length;
            bool match_standard = true;
            bool match_sans_accent = true;
            bool match_majuscule = true;
            
            for (size_t i = 0; i < query_length; i++) {
                if (str[offset + i] != d_query[i]) match_standard = false;
                if (str_sans_accent[offset + i] != d_query[i]) match_sans_accent = false;
                if (str_majuscule[offset + i] != d_query[i]) match_majuscule = false;
            }
            
            match = match_standard || match_sans_accent || match_majuscule;
        }
    }
    else { // "Contenant"
        for (size_t i = 0; i <= str_length - query_length; i++) {
            bool match_standard = true;
            bool match_sans_accent = true;
            bool match_majuscule = true;
            
            for (size_t j = 0; j < query_length; j++) {
                if (str[i + j] != d_query[j]) match_standard = false;
                if (str_sans_accent[i + j] != d_query[j]) match_sans_accent = false;
                if (str_majuscule[i + j] != d_query[j]) match_majuscule = false;
                
                if (!match_standard && !match_sans_accent && !match_majuscule) break;
            }
            
            if (match_standard || match_sans_accent || match_majuscule) {
                match = true;
                break;
            }
        }
    }
    
    d_results[idx] = match ? 1 : 0;
}

// Host helper functions to manage device memory and call kernels

// GPU implementation of levenshtein_n
extern "C" size_t cuda_levenshtein_n(const char *a, const size_t length, const char *b, const size_t bLength) {
    // Handle base cases
    if (a == b) return 0;
    if (!length) return bLength;
    if (!bLength) return length;
    
    // Allocate device memory
    char *d_a, *d_b;
    size_t *d_result, *d_length, *d_offset;
    cudaMalloc(&d_a, length);
    cudaMalloc(&d_b, bLength);
    cudaMalloc(&d_result, sizeof(size_t));
    cudaMalloc(&d_length, sizeof(size_t));
    cudaMalloc(&d_offset, sizeof(size_t));
    
    // Copy data to device
    cudaMemcpy(d_a, a, length, cudaMemcpyHostToDevice);
    cudaMemcpy(d_b, b, bLength, cudaMemcpyHostToDevice);
    
    size_t zero = 0;
    cudaMemcpy(d_offset, &zero, sizeof(size_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_length, &length, sizeof(size_t), cudaMemcpyHostToDevice);
    
    // Launch kernel with a single thread
    levenshtein_kernel<<<1, 1>>>(d_a, d_length, d_offset, d_b, bLength, d_result, 1);
    
    // Get result
    size_t h_result;
    cudaMemcpy(&h_result, d_result, sizeof(size_t), cudaMemcpyDeviceToHost);
    
    // Free device memory
    cudaFree(d_a);
    cudaFree(d_b);
    cudaFree(d_result);
    cudaFree(d_length);
    cudaFree(d_offset);
    
    return h_result;
}

// GPU implementation of levenshtein
extern "C" size_t cuda_levenshtein(const char *a, const char *b) {
    return cuda_levenshtein_n(a, strlen(a), b, strlen(b));
}

// GPU implementation of calculate_distances
extern "C" void cuda_calculate_distances(const char **names, size_t names_count, const char *query, size_t *distances, size_t min_distance, size_t max_suggestions) {
    // Prepare data for GPU
    size_t query_len = strlen(query);
    
    // Calculate total size needed for string data
    size_t total_size = 0;
    size_t* lengths = (size_t*)malloc(names_count * sizeof(size_t));
    size_t* offsets = (size_t*)malloc(names_count * sizeof(size_t));
    
    for (size_t i = 0; i < names_count; i++) {
        lengths[i] = strlen(names[i]);
        offsets[i] = total_size;
        total_size += lengths[i];
    }
    
    // Allocate memory for flattened string array
    char* h_flat_strings = (char*)malloc(total_size);
    
    // Flatten string array
    for (size_t i = 0; i < names_count; i++) {
        memcpy(h_flat_strings + offsets[i], names[i], lengths[i]);
    }
    
    // Allocate device memory
    char *d_flat_strings, *d_query;
    size_t *d_lengths, *d_offsets, *d_results, *d_temp_distances;
    
    cudaMalloc(&d_flat_strings, total_size);
    cudaMalloc(&d_query, query_len);
    cudaMalloc(&d_lengths, names_count * sizeof(size_t));
    cudaMalloc(&d_offsets, names_count * sizeof(size_t));
    cudaMalloc(&d_results, names_count * sizeof(size_t));
    cudaMalloc(&d_temp_distances, names_count * sizeof(size_t));
    
    // Copy data to device
    cudaMemcpy(d_flat_strings, h_flat_strings, total_size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_query, query, query_len, cudaMemcpyHostToDevice);
    cudaMemcpy(d_lengths, lengths, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_offsets, offsets, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    
    // Launch kernel
    int threadsPerBlock = 256;
    int blocksPerGrid = (names_count + threadsPerBlock - 1) / threadsPerBlock;
    
    levenshtein_kernel<<<blocksPerGrid, threadsPerBlock>>>(
        d_flat_strings, d_lengths, d_offsets, d_query, query_len, d_temp_distances, names_count
    );
    
    // Copy results back
    size_t* temp_distances = (size_t*)malloc(names_count * sizeof(size_t));
    cudaMemcpy(temp_distances, d_temp_distances, names_count * sizeof(size_t), cudaMemcpyDeviceToHost);
    
    // Process results on CPU side
    size_t suggestions_count = 0;
    for (size_t i = 0; i < names_count; i++) {
        if (temp_distances[i] < min_distance && suggestions_count < max_suggestions) {
            distances[suggestions_count++] = temp_distances[i];
        }
    }
    
    // Clean up
    free(h_flat_strings);
    free(lengths);
    free(offsets);
    free(temp_distances);
    
    cudaFree(d_flat_strings);
    cudaFree(d_query);
    cudaFree(d_lengths);
    cudaFree(d_offsets);
    cudaFree(d_results);
    cudaFree(d_temp_distances);
}

// GPU implementation of calculate_final_distances
extern "C" void cuda_calculate_final_distances(const char **names, size_t names_count, const char *query, size_t *distances) {
    // Prepare data similar to cuda_calculate_distances
    size_t query_len = strlen(query);
    
    // Calculate total size needed for string data
    size_t total_size = 0;
    size_t* lengths = (size_t*)malloc(names_count * sizeof(size_t));
    size_t* offsets = (size_t*)malloc(names_count * sizeof(size_t));
    
    for (size_t i = 0; i < names_count; i++) {
        lengths[i] = strlen(names[i]);
        offsets[i] = total_size;
        total_size += lengths[i];
    }
    
    // Allocate memory for flattened string array
    char* h_flat_strings = (char*)malloc(total_size);
    
    // Flatten string array
    for (size_t i = 0; i < names_count; i++) {
        memcpy(h_flat_strings + offsets[i], names[i], lengths[i]);
    }
    
    // Allocate device memory
    char *d_flat_strings, *d_query;
    size_t *d_lengths, *d_offsets, *d_distances;
    
    cudaMalloc(&d_flat_strings, total_size);
    cudaMalloc(&d_query, query_len);
    cudaMalloc(&d_lengths, names_count * sizeof(size_t));
    cudaMalloc(&d_offsets, names_count * sizeof(size_t));
    cudaMalloc(&d_distances, names_count * sizeof(size_t));
    
    // Copy data to device
    cudaMemcpy(d_flat_strings, h_flat_strings, total_size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_query, query, query_len, cudaMemcpyHostToDevice);
    cudaMemcpy(d_lengths, lengths, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_offsets, offsets, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    
    // Launch kernel
    int threadsPerBlock = 256;
    int blocksPerGrid = (names_count + threadsPerBlock - 1) / threadsPerBlock;
    
    levenshtein_kernel<<<blocksPerGrid, threadsPerBlock>>>(
        d_flat_strings, d_lengths, d_offsets, d_query, query_len, d_distances, names_count
    );
    
    // Copy results back
    cudaMemcpy(distances, d_distances, names_count * sizeof(size_t), cudaMemcpyDeviceToHost);
    
    // Clean up
    free(h_flat_strings);
    free(lengths);
    free(offsets);
    
    cudaFree(d_flat_strings);
    cudaFree(d_query);
    cudaFree(d_lengths);
    cudaFree(d_offsets);
    cudaFree(d_distances);
}

// GPU implementation of filter_df
extern "C" void cuda_filter_df(const char **names, const char **names_sans_accent, const char **names_majuscule, 
                            size_t names_count, const char *query, const char *search_type, int *results) {
    // Determine search type code
    int search_type_code;
    if (strcmp(search_type, "Commencant par") == 0)
        search_type_code = 0;
    else if (strcmp(search_type, "Finissant par") == 0)
        search_type_code = 1;
    else
        search_type_code = 2; // "Contenant"
    
    size_t query_len = strlen(query);
    
    // Calculate total size needed for string data
    size_t total_size = 0;
    size_t* lengths = (size_t*)malloc(names_count * sizeof(size_t));
    size_t* offsets = (size_t*)malloc(names_count * sizeof(size_t));
    
    for (size_t i = 0; i < names_count; i++) {
        lengths[i] = strlen(names[i]);
        offsets[i] = total_size;
        total_size += lengths[i];
    }
    
    // Allocate memory for flattened string arrays
    char* h_flat_strings = (char*)malloc(total_size);
    char* h_flat_sans_accent = (char*)malloc(total_size);
    char* h_flat_majuscule = (char*)malloc(total_size);
    
    // Flatten string arrays
    for (size_t i = 0; i < names_count; i++) {
        memcpy(h_flat_strings + offsets[i], names[i], lengths[i]);
        memcpy(h_flat_sans_accent + offsets[i], names_sans_accent[i], lengths[i]);
        memcpy(h_flat_majuscule + offsets[i], names_majuscule[i], lengths[i]);
    }
    
    // Allocate device memory
    char *d_flat_strings, *d_flat_sans_accent, *d_flat_majuscule, *d_query;
    size_t *d_lengths, *d_offsets;
    int *d_results;
    
    cudaMalloc(&d_flat_strings, total_size);
    cudaMalloc(&d_flat_sans_accent, total_size);
    cudaMalloc(&d_flat_majuscule, total_size);
    cudaMalloc(&d_query, query_len);
    cudaMalloc(&d_lengths, names_count * sizeof(size_t));
    cudaMalloc(&d_offsets, names_count * sizeof(size_t));
    cudaMalloc(&d_results, names_count * sizeof(int));
    
    // Copy data to device
    cudaMemcpy(d_flat_strings, h_flat_strings, total_size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_flat_sans_accent, h_flat_sans_accent, total_size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_flat_majuscule, h_flat_majuscule, total_size, cudaMemcpyHostToDevice);
    cudaMemcpy(d_query, query, query_len, cudaMemcpyHostToDevice);
    cudaMemcpy(d_lengths, lengths, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    cudaMemcpy(d_offsets, offsets, names_count * sizeof(size_t), cudaMemcpyHostToDevice);
    
    // Launch kernel
    int threadsPerBlock = 256;
    int blocksPerGrid = (names_count + threadsPerBlock - 1) / threadsPerBlock;
    
    filter_kernel<<<blocksPerGrid, threadsPerBlock>>>(
        d_flat_strings, d_flat_sans_accent, d_flat_majuscule, 
        d_lengths, d_offsets, d_query, query_len, 
        search_type_code, d_results, names_count
    );
    
    // Copy results back
    cudaMemcpy(results, d_results, names_count * sizeof(int), cudaMemcpyDeviceToHost);
    
    // Clean up
    free(h_flat_strings);
    free(h_flat_sans_accent);
    free(h_flat_majuscule);
    free(lengths);
    free(offsets);
    
    cudaFree(d_flat_strings);
    cudaFree(d_flat_sans_accent);
    cudaFree(d_flat_majuscule);
    cudaFree(d_query);
    cudaFree(d_lengths);
    cudaFree(d_offsets);
    cudaFree(d_results);
}
