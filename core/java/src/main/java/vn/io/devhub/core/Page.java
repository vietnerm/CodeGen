package vn.io.devhub.core;

import java.util.List;
import java.util.function.Function;

public record Page<T>(List<T> items, long total, int page, int size) {
    public <R> Page<R> map(Function<T, R> f) {
        return new Page<>(items.stream().map(f).toList(), total, page, size);
    }
}
