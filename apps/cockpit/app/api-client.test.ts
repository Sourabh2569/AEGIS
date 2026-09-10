import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiGet, authPost, clearToken, getToken, login, setToken } from "./api-client";

function mockFetchOnce(status: number, body: unknown) {
  const ok = status >= 200 && status < 300;
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "Error",
    json: async () => body,
  }) as unknown as typeof fetch;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("token storage", () => {
  it("round-trips through localStorage", () => {
    expect(getToken()).toBeNull();
    setToken("abc123");
    expect(getToken()).toBe("abc123");
    clearToken();
    expect(getToken()).toBeNull();
  });
});

describe("login", () => {
  it("returns the parsed response on success", async () => {
    mockFetchOnce(200, {
      access_token: "tok",
      token_type: "bearer",
      role: "FOUNDER",
      expires_in_minutes: 720,
    });
    const result = await login("cockpit_admin", "pw");
    expect(result.access_token).toBe("tok");
  });

  it("throws the backend's string detail on failure", async () => {
    mockFetchOnce(401, { detail: "Invalid username or password." });
    await expect(login("x", "y")).rejects.toThrow("Invalid username or password.");
  });

  it("falls back to a generic message when the error body isn't parseable", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    }) as unknown as typeof fetch;
    await expect(login("x", "y")).rejects.toThrow("Login failed");
  });
});

describe("apiGet", () => {
  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, { hello: "world" });
    const result = await apiGet("/api/v1/instruments", []);
    expect(result).toEqual({ hello: "world" });
  });

  it("returns the fallback on a non-ok response", async () => {
    mockFetchOnce(500, {});
    const result = await apiGet("/api/v1/instruments", ["fallback"]);
    expect(result).toEqual(["fallback"]);
  });

  it("returns the fallback when fetch itself throws", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("network down")) as unknown as typeof fetch;
    const result = await apiGet("/api/v1/instruments", "fallback-value");
    expect(result).toBe("fallback-value");
  });
});

describe("authPost", () => {
  it("includes the Authorization header when a token is present", async () => {
    setToken("real-token");
    mockFetchOnce(200, { ok: true });
    await authPost("/api/v1/research/momentum/run");
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer real-token");
  });

  it("omits the Authorization header when no token is present", async () => {
    mockFetchOnce(200, { ok: true });
    await authPost("/api/v1/research/momentum/run");
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("on a 401, clears the token, redirects to /login, and throws -- regression test for the dead-end token-expiry bug fixed this session", async () => {
    setToken("stale-token");
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign }, writable: true });
    mockFetchOnce(401, { detail: "Token has expired." });

    await expect(authPost("/api/v1/research/momentum/run")).rejects.toThrow(
      "Your session has expired",
    );
    expect(getToken()).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("surfaces a string detail on a non-401 error", async () => {
    mockFetchOnce(422, { detail: "Bad request." });
    await expect(authPost("/api/v1/paper-trade-intents/x/approve")).rejects.toThrow(
      "Bad request.",
    );
  });

  it("surfaces a structured detail's label on a non-401 error", async () => {
    mockFetchOnce(409, {
      detail: {
        state: "NO_REAL_HISTORICAL_DATA_CAPTURED",
        label: "No real historical EOD data has been captured yet",
      },
    });
    await expect(authPost("/api/v1/research/momentum/run")).rejects.toThrow(
      "No real historical EOD data has been captured yet",
    );
  });

  it("returns parsed JSON on success", async () => {
    mockFetchOnce(200, { decision_cycle_status: "COMPLETED" });
    const result = await authPost("/api/v1/paper-trading-sessions/run");
    expect(result).toEqual({ decision_cycle_status: "COMPLETED" });
  });
});
