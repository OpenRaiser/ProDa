import axios from "axios";

export const api = axios.create({
  baseURL: "/api",
  timeout: 120_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.data?.detail) {
      err.message = String(err.response.data.detail);
    }
    return Promise.reject(err);
  }
);
