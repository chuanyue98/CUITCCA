def bubble_sort_descending(arr):
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - 1 - i):
            if arr[j] < arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]

# 示例用法
my_list = [1,2,3,4,4,5,6,7,8,9,10]
bubble_sort_descending(my_list)
print(my_list)