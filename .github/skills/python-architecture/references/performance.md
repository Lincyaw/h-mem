# Performance Optimization Reference

## Profiling and Measurement

### Basic Profiling

Always profile before optimizing:

```python
import cProfile
import pstats
from io import StringIO

def profile_code(func):
    """Profile function execution."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = func()
    
    profiler.disable()
    
    # Print stats
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 functions
    print(stream.getvalue())
    
    return result

# Usage
def expensive_function():
    # Code to profile
    pass

result = profile_code(expensive_function)
```

### Line Profiling

Profile line-by-line execution:

```python
# Install: pip install line-profiler
from line_profiler import LineProfiler

def profile_lines(func):
    """Profile function line by line."""
    profiler = LineProfiler()
    profiler.add_function(func)
    profiler.enable()
    
    result = func()
    
    profiler.disable()
    profiler.print_stats()
    
    return result
```

### Memory Profiling

Track memory usage:

```python
# Install: pip install memory-profiler
from memory_profiler import profile

@profile
def memory_intensive_function():
    """Function with memory profiling."""
    data = [i for i in range(1000000)]
    processed = [x * 2 for x in data]
    return sum(processed)
```

### Timing Code

Measure execution time:

```python
import time
from functools import wraps

def timeit(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f} seconds")
        return result
    return wrapper

@timeit
def process_data(data: list[int]) -> int:
    return sum(x * 2 for x in data)

# For quick benchmarks
from timeit import timeit

# Test different approaches
time1 = timeit('sum([x*2 for x in range(1000)])', number=10000)
time2 = timeit('sum(x*2 for x in range(1000))', number=10000)
print(f"List comprehension: {time1:.4f}s")
print(f"Generator: {time2:.4f}s")
```

## Algorithm Optimization

### Choose Right Data Structure

```python
# ❌ O(n) lookup in list
def find_user_slow(users: list[User], user_id: str) -> User | None:
    for user in users:
        if user.id == user_id:
            return user
    return None

# ✅ O(1) lookup in dict
def find_user_fast(users: dict[str, User], user_id: str) -> User | None:
    return users.get(user_id)

# ❌ O(n) membership test
if item in item_list:  # list
    pass

# ✅ O(1) membership test
if item in item_set:  # set
    pass
```

### Avoid Repeated Computation

```python
# ❌ Recompute same value
def calculate_metrics(data: list[float]) -> dict[str, float]:
    return {
        'mean': sum(data) / len(data),
        'variance': sum((x - sum(data)/len(data))**2 for x in data) / len(data),
    }

# ✅ Compute once, reuse
def calculate_metrics(data: list[float]) -> dict[str, float]:
    mean = sum(data) / len(data)
    variance = sum((x - mean)**2 for x in data) / len(data)
    return {'mean': mean, 'variance': variance}
```

### Use Appropriate Algorithms

```python
import bisect

# ❌ O(n) search in sorted list
def find_in_sorted_slow(items: list[int], target: int) -> int:
    for i, item in enumerate(items):
        if item == target:
            return i
    return -1

# ✅ O(log n) binary search
def find_in_sorted_fast(items: list[int], target: int) -> int:
    index = bisect.bisect_left(items, target)
    if index < len(items) and items[index] == target:
        return index
    return -1
```

## NumPy Vectorization

### Replace Loops with NumPy

```python
import numpy as np
from numpy.typing import NDArray

# ❌ Slow Python loop
def moving_average_slow(data: list[float], window: int) -> list[float]:
    result = []
    for i in range(len(data) - window + 1):
        window_data = data[i:i + window]
        result.append(sum(window_data) / window)
    return result

# ✅ Fast NumPy vectorization
def moving_average_fast(
    data: NDArray[np.float64],
    window: int
) -> NDArray[np.float64]:
    return np.convolve(data, np.ones(window)/window, mode='valid')

# Benchmark
import timeit
data_list = list(range(10000))
data_array = np.array(data_list, dtype=np.float64)

slow_time = timeit.timeit(lambda: moving_average_slow(data_list, 100), number=100)
fast_time = timeit.timeit(lambda: moving_average_fast(data_array, 100), number=100)
print(f"Speedup: {slow_time/fast_time:.1f}x")
```

### Broadcasting

```python
import numpy as np

# ❌ Explicit loops
def normalize_slow(data: NDArray[np.float64]) -> NDArray[np.float64]:
    mean = data.mean()
    std = data.std()
    result = np.empty_like(data)
    for i in range(len(data)):
        result[i] = (data[i] - mean) / std
    return result

# ✅ Broadcasting
def normalize_fast(data: NDArray[np.float64]) -> NDArray[np.float64]:
    return (data - data.mean()) / data.std()

# Matrix operations
# ❌ Element-wise loops
def matrix_multiply_slow(A: NDArray, B: NDArray) -> NDArray:
    result = np.zeros((A.shape[0], B.shape[1]))
    for i in range(A.shape[0]):
        for j in range(B.shape[1]):
            for k in range(A.shape[1]):
                result[i, j] += A[i, k] * B[k, j]
    return result

# ✅ NumPy built-in
def matrix_multiply_fast(A: NDArray, B: NDArray) -> NDArray:
    return A @ B  # or np.matmul(A, B)
```

### Boolean Indexing

```python
import numpy as np

# ❌ Filter with loops
def filter_outliers_slow(data: list[float], threshold: float) -> list[float]:
    return [x for x in data if abs(x) < threshold]

# ✅ Boolean indexing
def filter_outliers_fast(
    data: NDArray[np.float64],
    threshold: float
) -> NDArray[np.float64]:
    return data[np.abs(data) < threshold]
```

## Caching and Memoization

### functools.lru_cache

```python
from functools import lru_cache

# ❌ Repeated computation
def fibonacci_slow(n: int) -> int:
    if n < 2:
        return n
    return fibonacci_slow(n-1) + fibonacci_slow(n-2)

# ✅ Cached results
@lru_cache(maxsize=128)
def fibonacci_fast(n: int) -> int:
    if n < 2:
        return n
    return fibonacci_fast(n-1) + fibonacci_fast(n-2)

# Custom caching
from functools import wraps

def cache_results(func):
    """Custom caching decorator."""
    cache = {}
    
    @wraps(func)
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]
    
    return wrapper

@cache_results
def expensive_computation(x: int, y: int) -> int:
    # Expensive calculation
    return x ** y
```

### Instance-Level Caching

```python
from functools import cached_property

class DataAnalyzer:
    def __init__(self, data: list[float]):
        self._data = data
    
    @cached_property
    def mean(self) -> float:
        """Compute mean once, cache result."""
        return sum(self._data) / len(self._data)
    
    @cached_property
    def std(self) -> float:
        """Compute std once, cache result."""
        variance = sum((x - self.mean)**2 for x in self._data) / len(self._data)
        return variance ** 0.5
```

## Generator Expressions

### Memory-Efficient Iteration

```python
# ❌ Load everything into memory
def process_large_file_slow(filename: str) -> int:
    lines = open(filename).readlines()  # Loads entire file
    numbers = [int(line.strip()) for line in lines]
    return sum(numbers)

# ✅ Stream processing
def process_large_file_fast(filename: str) -> int:
    with open(filename) as f:
        numbers = (int(line.strip()) for line in f)  # Generator
        return sum(numbers)

# ❌ Build intermediate list
def get_large_squares(n: int) -> list[int]:
    squares = [x**2 for x in range(n)]
    return [x for x in squares if x > 1000]

# ✅ Chain generators
def get_large_squares(n: int) -> list[int]:
    squares = (x**2 for x in range(n))
    return [x for x in squares if x > 1000]
```

### Lazy Evaluation

```python
from typing import Iterator

def read_chunks(filename: str, chunk_size: int = 1024) -> Iterator[bytes]:
    """Lazily read file in chunks."""
    with open(filename, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

# Process data lazily
def process_data_stream(data: Iterator[dict]) -> Iterator[dict]:
    """Transform data stream without loading all into memory."""
    for item in data:
        if item['value'] > 0:
            yield {'id': item['id'], 'doubled': item['value'] * 2}
```

## String Operations

### String Building

```python
# ❌ Repeated string concatenation O(n²)
def build_string_slow(items: list[str]) -> str:
    result = ""
    for item in items:
        result += item + ", "
    return result

# ✅ Join operation O(n)
def build_string_fast(items: list[str]) -> str:
    return ", ".join(items)

# For complex building
from io import StringIO

def build_complex_string(data: list[dict]) -> str:
    buffer = StringIO()
    for item in data:
        buffer.write(f"{item['name']}: {item['value']}\n")
    return buffer.getvalue()
```

## Database Optimization

### Batch Operations

```python
# ❌ Individual inserts
def save_users_slow(users: list[User], session: Session) -> None:
    for user in users:
        session.add(user)
        session.commit()  # Commit each time

# ✅ Batch insert
def save_users_fast(users: list[User], session: Session) -> None:
    session.add_all(users)
    session.commit()  # Single commit

# ✅ Bulk operations
def update_status_fast(user_ids: list[str], session: Session) -> None:
    session.query(User).filter(
        User.id.in_(user_ids)
    ).update({'is_active': True}, synchronize_session=False)
    session.commit()
```

### Query Optimization

```python
# ❌ N+1 queries
def get_users_with_posts_slow(session: Session) -> list[User]:
    users = session.query(User).all()
    for user in users:
        posts = user.posts  # Lazy load triggers query per user
    return users

# ✅ Eager loading
from sqlalchemy.orm import joinedload

def get_users_with_posts_fast(session: Session) -> list[User]:
    return session.query(User).options(
        joinedload(User.posts)
    ).all()  # Single query with join
```

## Async Optimization

### Concurrent I/O

```python
import asyncio
import aiohttp
from typing import Sequence

# ❌ Sequential I/O
async def fetch_all_slow(urls: Sequence[str]) -> list[str]:
    results = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            async with session.get(url) as response:
                results.append(await response.text())
    return results

# ✅ Concurrent I/O
async def fetch_all_fast(urls: Sequence[str]) -> list[str]:
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_url(session, url) for url in urls]
        return await asyncio.gather(*tasks)

async def fetch_url(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url) as response:
        return await response.text()
```

## Optimization Checklist

When optimizing performance:

1. **Profile first** - Identify actual bottlenecks
2. **Algorithm complexity** - Reduce O(n²) to O(n log n) or O(n)
3. **Data structures** - Use dict/set for lookups, not lists
4. **Vectorization** - Replace loops with NumPy operations
5. **Caching** - Memoize expensive computations
6. **Generators** - Use for large datasets
7. **Batch operations** - Database/API calls in batches
8. **Async I/O** - Concurrent network/file operations
9. **Compile** - Consider Cython/Numba for hot loops
10. **Profile again** - Verify improvements

## Common Pitfalls

```python
# ❌ Premature optimization
def overly_optimized_but_unreadable():
    pass

# ✅ Clear code first, optimize if needed
def clear_and_fast_enough():
    pass

# ❌ Micro-optimizations
x = x + 1  # Don't change to x += 1 expecting speedup

# ✅ Focus on algorithmic improvements
# O(n) instead of O(n²)
```
