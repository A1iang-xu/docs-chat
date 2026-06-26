# Vue 3 Reactivity Guide

## Introduction

Vue's reactivity system is one of its core features. It allows you to declare reactive state that automatically triggers updates when changed. Vue 3's reactivity is built on JavaScript Proxies, making it more powerful and predictable than Vue 2's Object.defineProperty-based approach.

## ref()

`ref()` is the main API for creating reactive references. It wraps any value (primitive or object) and returns a reactive ref object. You access the value via the `.value` property.

```javascript
import { ref } from 'vue'

const count = ref(0)
console.log(count.value) // 0
count.value++
console.log(count.value) // 1
```

The `ref()` function returns a reactive ref object with a single property `.value` that points to the inner value. When the value is an object, `ref()` will call `reactive()` internally.

### ref() return type

`ref()` returns a RefImpl object. The `.value` property is reactive. The type is `Ref<T>` where T is the type of the inner value. Template auto-unwrapping applies: in templates, you can use `count` directly without `.value`.

## reactive()

`reactive()` creates a proxy of the original object. Unlike `ref()`, it only works with object types (objects, arrays, Map, Set). You access properties directly without `.value`.

```javascript
import { reactive } from 'vue'

const state = reactive({
  count: 0,
  name: 'Vue'
})

state.count++ // reactive, no .value needed
```

### ref vs reactive

Use `ref()` for primitives and single values. Use `reactive()` for objects with multiple properties. A common pattern is to use `ref()` for simple values and `reactive()` for form state or complex objects.

## computed()

`computed()` creates a computed property that caches its result and only re-evaluates when dependencies change.

```javascript
import { ref, computed } from 'vue'

const count = ref(1)
const double = computed(() => count.value * 2)
console.log(double.value) // 2
count.value = 3
console.log(double.value) // 6
```

Computed properties are readonly by default. To create a writable computed, pass an object with `get` and `set` functions:

```javascript
const fullName = computed({
  get() { return firstName.value + ' ' + lastName.value },
  set(newValue) {
    [firstName.value, lastName.value] = newValue.split(' ')
  }
})
```

## watch()

`watch()` observes reactive sources and runs a callback when they change. It supports watching refs, reactive objects, getter functions, and arrays of sources.

```javascript
import { ref, watch } from 'vue'

const count = ref(0)
watch(count, (newValue, oldValue) => {
  console.log(`changed from ${oldValue} to ${newValue}`)
})
```

### watch vs watchEffect

`watch()` is lazy by default (callback only runs when the source changes). `watchEffect()` runs immediately and automatically tracks dependencies. Use `watch()` when you need access to old/new values or want explicit control over what to watch. Use `watchEffect()` for side effects with automatic dependency tracking.

## Lifecycle Hooks

Vue 3 composition API lifecycle hooks correspond to the options API lifecycle hooks. The main hooks are:

- `onBeforeMount()` - called before the component is mounted
- `onMounted()` - called after the component is mounted
- `onBeforeUpdate()` - called before reactive data changes the DOM
- `onUpdated()` - called after reactive data changes the DOM
- `onBeforeUnmount()` - called before the component is unmounted
- `onUnmounted()` - called after the component is unmounted

```javascript
import { onMounted, onUnmounted } from 'vue'

onMounted(() => {
  console.log('Component is mounted')
})

onUnmounted(() => {
  console.log('Component is unmounted')
})
```

## Composition API

The Composition API is a set of APIs that allows you to organize component logic using function-based APIs rather than the options-based API. It provides better type inference, better code organization for complex components, and better reusability through composables.

### Writing a composable

A composable is a function that encapsulates reusable reactive logic. Here is how to write a composable for a mouse tracker:

```javascript
import { ref, onMounted, onUnmounted } from 'vue'

export function useMouse() {
  const x = ref(0)
  const y = ref(0)

  function update(event) {
    x.value = event.pageX
    y.value = event.pageY
  }

  onMounted(() => window.addEventListener('mousemove', update))
  onUnmounted(() => window.removeEventListener('mousemove', update))

  return { x, y }
}
```

Use the composable in a component:

```vue
<script setup>
import { useMouse } from './composables/useMouse'

const { x, y } = useMouse()
</script>

<template>
  Mouse position: {{ x }}, {{ y }}
</template>
```
