
#include <algorithm>
#include <iostream>
#include <vector>

template <typename T>
void quicksort(std::vector<T>& arr, int left, int right) {
    int i = left, j = right;
    T pivot = arr[(left + right) / 2];

    // Partition
    while (i <= j) {
        while (arr[i] < pivot)
            i++;
        while (arr[j] > pivot)
            j--;
        if (i <= j) {
            std::swap(arr[i], arr[j]);
            i++;
            j--;
        }
    }

    // Recursion
    if (left < j)
        quicksort(arr, left, j);
    if (i < right)
        quicksort(arr, i, right);
}

int main() {
    std::vector<int> arr = {35, 12, 8, 99, 21, 5};

    quicksort(arr, 0, arr.size() - 1);

    for (int i = 0; i < arr.size(); i++)
        std::cout << arr[i] << " ";
    std::cout << std::endl;

    return 0;
}
