import { resolveServiceBaseUrl } from "../lib/serviceBaseUrls";

describe("service base URL resolution", () => {
  it("uses public API defaults on hosted domains when Vercel env values are blank", () => {
    expect(resolveServiceBaseUrl("", "strategy", "app.apexpark.io")).toBe(
      "https://api.apexpark.io/strategy"
    );
    expect(resolveServiceBaseUrl("   ", "execution", "cryptopairs-preview.vercel.app")).toBe(
      "https://api.apexpark.io/execution"
    );
    expect(resolveServiceBaseUrl(undefined, "account", "app.apexpark.io")).toBe(
      "https://api.apexpark.io/account"
    );
  });

  it("keeps localhost defaults for local development when env values are blank", () => {
    expect(resolveServiceBaseUrl("", "strategy", "localhost")).toBe("http://127.0.0.1:8083");
    expect(resolveServiceBaseUrl("", "execution", "127.0.0.1")).toBe("http://127.0.0.1:8082");
    expect(resolveServiceBaseUrl("", "account", "[::1]")).toBe("http://127.0.0.1:8081");
  });

  it("uses explicit nonblank environment values and trims trailing slashes", () => {
    expect(
      resolveServiceBaseUrl(" https://custom.example/strategy/ ", "strategy", "app.apexpark.io")
    ).toBe("https://custom.example/strategy");
  });
});
