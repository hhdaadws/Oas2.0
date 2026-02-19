<template>
  <div class="app-root">
    <div class="decor decor--a" />
    <div class="decor decor--b" />

    <component
      :is="currentComponent"
      :session="session"
      @navigate="navigate"
      @session-updated="refreshSession"
    />
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import LoginPage from "./pages/LoginPage.vue";
const ManagerPage = defineAsyncComponent(() => import("./pages/ManagerPage.vue"));
const UserPage = defineAsyncComponent(() => import("./pages/UserPage.vue"));
const SuperAdminLoginPage = defineAsyncComponent(() => import("./pages/SuperAdminLoginPage.vue"));
const SuperAdminPage = defineAsyncComponent(() => import("./pages/SuperAdminPage.vue"));
import { getSession } from "./lib/session";

const ROUTES = new Set(["/login", "/manager", "/user", "/super-admin-login", "/super-admin"]);

const currentPath = ref(resolvePath(window.location.pathname));
const session = reactive(getSession());

const currentComponent = computed(() => {
  if (currentPath.value === "/manager") {
    return ManagerPage;
  }
  if (currentPath.value === "/user") {
    return UserPage;
  }
  if (currentPath.value === "/super-admin-login") {
    return SuperAdminLoginPage;
  }
  if (currentPath.value === "/super-admin") {
    return SuperAdminPage;
  }
  return LoginPage;
});

watch(
  [currentPath, () => session.managerToken, () => session.userToken, () => session.superToken],
  ([path, managerToken, userToken, superToken]) => {
    if (path === "/manager" && !managerToken) {
      navigate("/login", { replace: true });
      return;
    }
    if (path === "/user" && !userToken) {
      navigate("/login", { replace: true });
      return;
    }
    if (path === "/super-admin" && !superToken) {
      navigate("/super-admin-login", { replace: true });
      return;
    }
    if (path === "/super-admin-login" && superToken) {
      navigate("/super-admin", { replace: true });
    }
  },
  { immediate: true },
);

onMounted(() => {
  if (window.location.pathname === "/") {
    navigate("/login", { replace: true });
  }
  window.addEventListener("popstate", onPopState);
});

onBeforeUnmount(() => {
  window.removeEventListener("popstate", onPopState);
});

function onPopState() {
  currentPath.value = resolvePath(window.location.pathname);
  refreshSession();
}

function refreshSession() {
  Object.assign(session, getSession());
}

function navigate(path, options = {}) {
  const resolved = resolvePath(path);
  if (options.replace) {
    window.history.replaceState({}, "", resolved);
  } else if (window.location.pathname !== resolved) {
    window.history.pushState({}, "", resolved);
  }
  currentPath.value = resolved;
  refreshSession();
}

function resolvePath(path) {
  const trimmed = path?.trim() || "/";
  const normalized = trimmed.endsWith("/") && trimmed !== "/" ? trimmed.slice(0, -1) : trimmed;
  if (normalized === "/") {
    return "/login";
  }
  return ROUTES.has(normalized) ? normalized : "/login";
}
</script>
