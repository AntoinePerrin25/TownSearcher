#include <string.h>
#include <stdlib.h>
#include <stdint.h>

// Returns a size_t, depicting the difference between `a` and `b`.
// See <https://en.wikipedia.org/wiki/Levenshtein_distance> for more information.
size_t levenshtein_n(const char *a, const size_t length, const char *b, const size_t bLength) {
  // Shortcut optimizations / degenerate cases.
  if (a == b) {return 0;}
  if (!length) {return bLength;}
  if (!bLength) {return length;}

  size_t *cache = calloc(length, sizeof(size_t));
  size_t index = 0;size_t bIndex = 0;
  size_t distance;size_t bDistance;size_t result;
  char code;

  while (index < length) {
    cache[index] = index + 1;
    index++;
  }

  while (bIndex < bLength) {
    code = b[bIndex];
    result = distance = bIndex++;
    index = SIZE_MAX;

    while (++index < length) {
      bDistance = code == a[index] ? distance : distance + 1;
      distance = cache[index];

      cache[index] = result = distance > result
        ? bDistance > result
          ? result + 1
          : bDistance
        : bDistance > distance
          ? distance + 1
          : bDistance;
  }}
  free(cache);
  return result;
}

size_t levenshtein(const char *a, const char *b) {
  const size_t length = strlen(a);
  const size_t bLength = strlen(b);

  return levenshtein_n(a, length, b, bLength);
}

void calculate_distances(const char **names, size_t names_count, const char *query, size_t *distances, size_t min_distance, size_t max_suggestions) {
    size_t *temp_distances = malloc(names_count * sizeof(size_t));
    size_t suggestions_count = 0;

    for (size_t i = 0; i < names_count; i++) {
        temp_distances[i] = levenshtein(names[i], query);
    }

    for (size_t i = 0; i < names_count; i++) {
        if (temp_distances[i] < min_distance && suggestions_count < max_suggestions) {
            distances[suggestions_count++] = temp_distances[i];
        }
    }

    free(temp_distances);
}

void calculate_final_distances(const char **names, size_t names_count, const char *query, size_t *distances) {
    for (size_t i = 0; i < names_count; i++) {
        distances[i] = levenshtein(names[i], query);
    }
}

void filter_df(const char **names, const char **names_sans_accent, const char **names_majuscule, size_t names_count, const char *query, const char *search_type, int *results) {
    for (size_t i = 0; i < names_count; i++) {
        if (strcmp(search_type, "Commencant par") == 0) {
            if (strncmp(names[i], query, strlen(query)) == 0 ||
                strncmp(names_sans_accent[i], query, strlen(query)) == 0 ||
                strncmp(names_majuscule[i], query, strlen(query)) == 0) {
                results[i] = 1;
            } else {
                results[i] = 0;
            }
        } else if (strcmp(search_type, "Finissant par") == 0) {
            size_t name_len = strlen(names[i]);
            size_t query_len = strlen(query);
            if ((name_len >= query_len && strcmp(names[i] + name_len - query_len, query) == 0) ||
                (name_len >= query_len && strcmp(names_sans_accent[i] + name_len - query_len, query) == 0) ||
                (name_len >= query_len && strcmp(names_majuscule[i] + name_len - query_len, query) == 0)) {
                results[i] = 1;
            } else {
                results[i] = 0;
            }
        } else { // Contenant
            if (strstr(names[i], query) != NULL ||
                strstr(names_sans_accent[i], query) != NULL ||
                strstr(names_majuscule[i], query) != NULL) {
                results[i] = 1;
            } else {
                results[i] = 0;
            }
        }
    }
}