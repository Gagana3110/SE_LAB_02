import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { ADMIN, BUYER, error, fakeServer, INVENTORY, PLANNER } from "./testServer";

const STEEL = { id: 1, code: "M001", name: "Steel", unit: "kg", category: null, active: true };
const PAINT = { id: 2, code: "M002", name: "Paint", unit: "litre", category: null, active: true };
const CHAIR = { id: 7, code: "P001", name: "Chair", unit: "piece", category: "Furniture", active: true };
const ACME = {
  id: 3,
  code: "S01",
  name: "Acme",
  lead_time_days: 7,
  moq: 100,
  unit_price: 12.5,
  monthly_capacity: 5000,
  reliability_pct: 90,
  active: true,
};

function open(path = "/") {
  window.history.pushState({}, "", path);
  render(<App />);
}

const menuLabels = async () => {
  const menu = await screen.findByRole("navigation", { name: "Main menu" });
  return within(menu)
    .getAllByRole("link")
    .map((link) => link.textContent);
};

describe("login", () => {
  it("shows the login page when there is no session", async () => {
    fakeServer({ "GET /auth/me": error(401, "Not authenticated") });
    open();
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("logs in and opens the app", async () => {
    const server = fakeServer({
      "GET /auth/me": error(401, "Not authenticated"),
      "POST /auth/login": { body: PLANNER },
      "GET /products": { body: [CHAIR] },
    });
    open();
    await userEvent.type(await screen.findByLabelText("Email"), PLANNER.email);
    await userEvent.type(screen.getByLabelText("Password"), "a-password");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("heading", { name: "Products" })).toBeInTheDocument();
    expect(server.bodyOf("POST /auth/login")).toEqual({
      email: PLANNER.email,
      password: "a-password",
    });
  });

  it("shows the server's message when login fails and allows a retry", async () => {
    fakeServer({
      "GET /auth/me": error(401, "Not authenticated"),
      "POST /auth/login": error(401, "Invalid email or password, or the account is temporarily locked"),
    });
    open();
    await userEvent.type(await screen.findByLabelText("Email"), "x@dfs-demo.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeEnabled();
  });

  it("logs out", async () => {
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /products": { body: [] },
      "POST /auth/logout": { status: 204 },
    });
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });

  it("returns to login when the session expires", async () => {
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /products": error(401, "Not authenticated"),
    });
    open();
    expect(await screen.findByRole("button", { name: "Log in" })).toBeInTheDocument();
  });
});

describe("menus follow the role", () => {
  it.each([
    [ADMIN, ["Products", "Raw materials", "Suppliers", "Forecast", "Users"]],
    [PLANNER, ["Products", "Raw materials", "Import sales", "Forecast"]],
    [INVENTORY, ["Products", "Raw materials", "Forecast"]],
    [BUYER, ["Products", "Raw materials", "Suppliers", "Forecast"]],
  ])("for $role", async (user, expected) => {
    fakeServer({ "GET /auth/me": { body: user }, "GET /products": { body: [] } });
    open();
    expect(await menuLabels()).toEqual(expected);
  });

  it.each(["/users", "/suppliers", "/materials/1/suppliers"])(
    "blocks a planner typing the address %s",
    async (path) => {
      const server = fakeServer({ "GET /auth/me": { body: PLANNER } });
      open(path);
      expect(await screen.findByRole("heading", { name: "No access" })).toBeInTheDocument();
      expect(server.calls.map((call) => call.key)).toEqual(["GET /auth/me"]);
    },
  );

  it("blocks an admin from the import page", async () => {
    fakeServer({ "GET /auth/me": { body: ADMIN } });
    open("/import");
    expect(await screen.findByRole("heading", { name: "No access" })).toBeInTheDocument();
  });
});

describe("products and raw materials", () => {
  it("lets an admin add an item", async () => {
    let items: unknown[] = [CHAIR];
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /materials": () => ({ body: items }),
      "POST /materials": () => {
        items = [STEEL];
        return { status: 201, body: STEEL };
      },
    });
    open("/materials");
    await userEvent.type(await screen.findByLabelText("Code"), "M001");
    await userEvent.type(screen.getByLabelText("Name"), "Steel");
    await userEvent.type(screen.getByLabelText("Unit"), "kg");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("cell", { name: "Steel" })).toBeInTheDocument();
    expect(server.bodyOf("POST /materials")).toEqual({
      code: "M001",
      name: "Steel",
      unit: "kg",
      category: null,
    });
  });

  it("shows a duplicate-code error and keeps what was typed", async () => {
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /products": { body: [] },
      "POST /products": error(409, "This code is already in use"),
    });
    open("/products");
    await userEvent.type(await screen.findByLabelText("Code"), "P001");
    await userEvent.type(screen.getByLabelText("Name"), "Chair");
    await userEvent.type(screen.getByLabelText("Unit"), "piece");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already in use");
    expect(screen.getByLabelText("Code")).toHaveValue("P001");
  });

  it("edits an item", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /products": { body: [CHAIR] },
      "PATCH /products/7": { body: CHAIR },
    });
    open("/products");
    await userEvent.click(await screen.findByRole("button", { name: "Edit P001" }));
    const name = screen.getByLabelText("Name");
    expect(name).toHaveValue("Chair");
    await userEvent.clear(name);
    await userEvent.type(name, "Stool");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(server.bodyOf("PATCH /products/7").name).toBe("Stool"));
  });

  it("deactivates an item", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /products": { body: [CHAIR] },
      "PATCH /products/7": { body: { ...CHAIR, active: false } },
    });
    open("/products");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate P001" }));
    await waitFor(() => expect(server.bodyOf("PATCH /products/7")).toEqual({ active: false }));
  });

  it("is read-only for other roles", async () => {
    fakeServer({ "GET /auth/me": { body: INVENTORY }, "GET /products": { body: [CHAIR] } });
    open("/products");
    expect(await screen.findByRole("cell", { name: "Chair" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit/ })).not.toBeInTheDocument();
  });
});

describe("bill of materials", () => {
  const routes = {
    "GET /auth/me": { body: ADMIN },
    "GET /products/7": { body: CHAIR },
    "GET /materials?active_only=true": { body: [STEEL, PAINT] },
    "GET /products/7/bom": { body: [{ material: STEEL, qty_per_unit: 2.5 }] },
  };

  it("loads the BOM, adds a line and saves", async () => {
    const server = fakeServer({ ...routes, "PUT /products/7/bom": { body: [] } });
    open("/products/7/bom");
    expect(await screen.findByLabelText("Quantity for line 1")).toHaveValue(2.5);
    await userEvent.click(screen.getByRole("button", { name: "Add line" }));
    await userEvent.selectOptions(screen.getByLabelText("Material for line 2"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Save BOM" }));
    expect(await screen.findByRole("status")).toHaveTextContent("BOM saved");
    expect(server.bodyOf("PUT /products/7/bom")).toEqual({
      lines: [
        { material_id: 1, qty_per_unit: "2.5" },
        { material_id: 2, qty_per_unit: "1" },
      ],
    });
  });

  it("asks for a material before saving", async () => {
    const server = fakeServer(routes);
    open("/products/7/bom");
    await userEvent.click(await screen.findByRole("button", { name: "Add line" }));
    await userEvent.click(screen.getByRole("button", { name: "Save BOM" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a material");
    expect(server.calls.some((call) => call.key.startsWith("PUT"))).toBe(false);
  });

  it("shows server validation errors and removes lines", async () => {
    const server = fakeServer({
      ...routes,
      "PUT /products/7/bom": error(400, "Invalid request", [
        { field: "lines.0.qty_per_unit", message: "must be greater than 0" },
      ]),
    });
    open("/products/7/bom");
    await userEvent.click(await screen.findByRole("button", { name: "Save BOM" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("must be greater than 0");
    await userEvent.click(screen.getByRole("button", { name: "Remove line 1" }));
    expect(screen.getByText("No materials in this BOM yet.")).toBeInTheDocument();
    expect(server.calls.length).toBeGreaterThan(0);
  });

  it("is read-only for other roles", async () => {
    fakeServer({ ...routes, "GET /auth/me": { body: PLANNER } });
    open("/products/7/bom");
    expect(await screen.findByRole("cell", { name: "M001 Steel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save BOM" })).not.toBeInTheDocument();
  });
});

describe("suppliers", () => {
  it("adds a supplier and warns about materials with no supplier", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /suppliers": { body: [ACME] },
      "GET /purchasing/materials-without-supplier": { body: [PAINT] },
      "POST /suppliers": { status: 201, body: ACME },
    });
    open("/suppliers");
    expect(await screen.findByRole("link", { name: "M002" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "12.50" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Code"), "S02");
    await userEvent.type(screen.getByLabelText("Name"), "Beta");
    await userEvent.type(screen.getByLabelText("Lead time (days)"), "5");
    await userEvent.type(screen.getByLabelText("Minimum order quantity"), "10");
    await userEvent.type(screen.getByLabelText("Unit price"), "9.5");
    await userEvent.type(screen.getByLabelText("Monthly capacity"), "100");
    await userEvent.type(screen.getByLabelText("On-time delivery (%)"), "80");
    await userEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(server.bodyOf("POST /suppliers").code).toBe("S02"));
  });

  it("edits and deactivates a supplier", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /suppliers": { body: [ACME] },
      "GET /purchasing/materials-without-supplier": { body: [] },
      "PATCH /suppliers/3": { body: ACME },
    });
    open("/suppliers");
    await userEvent.click(await screen.findByRole("button", { name: "Deactivate S01" }));
    await waitFor(() => expect(server.bodyOf("PATCH /suppliers/3")).toEqual({ active: false }));
    await userEvent.click(screen.getByRole("button", { name: "Edit S01" }));
    expect(screen.getByLabelText("Lead time (days)")).toHaveValue(7);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(server.bodyOf("PATCH /suppliers/3").code).toBe("S01"));
  });

  it("shows server errors on the form", async () => {
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /suppliers": { body: [ACME] },
      "GET /purchasing/materials-without-supplier": { body: [] },
      "PATCH /suppliers/3": error(409, "This code is already in use"),
    });
    open("/suppliers");
    await userEvent.click(await screen.findByRole("button", { name: "Edit S01" }));
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already in use");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("is read-only for procurement", async () => {
    fakeServer({
      "GET /auth/me": { body: BUYER },
      "GET /suppliers": { body: [ACME] },
      "GET /purchasing/materials-without-supplier": { body: [] },
    });
    open("/suppliers");
    expect(await screen.findByRole("cell", { name: "Acme" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Code")).not.toBeInTheDocument();
  });

  it("links suppliers to a material with one preferred", async () => {
    const beta = { ...ACME, id: 4, code: "S02", name: "Beta" };
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /materials/1": { body: STEEL },
      "GET /suppliers?active_only=true": { body: [ACME, beta] },
      "GET /materials/1/suppliers": { body: [{ supplier: ACME, preferred: true }] },
      "PUT /materials/1/suppliers": { body: [] },
    });
    open("/materials/1/suppliers");
    expect(await screen.findByLabelText("Approve S01")).toBeChecked();
    expect(screen.getByLabelText("Prefer S02")).toBeDisabled();
    await userEvent.click(screen.getByLabelText("Approve S02"));
    await userEvent.click(screen.getByLabelText("Prefer S02"));
    await userEvent.click(screen.getByRole("button", { name: "Save suppliers" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Suppliers saved");
    expect(server.bodyOf("PUT /materials/1/suppliers")).toEqual({
      links: [
        { supplier_id: 3, preferred: false },
        { supplier_id: 4, preferred: true },
      ],
    });
  });

  it("moves preferred when the preferred supplier is removed", async () => {
    const beta = { ...ACME, id: 4, code: "S02", name: "Beta" };
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /materials/1": { body: STEEL },
      "GET /suppliers?active_only=true": { body: [ACME, beta] },
      "GET /materials/1/suppliers": {
        body: [
          { supplier: ACME, preferred: true },
          { supplier: beta, preferred: false },
        ],
      },
      "PUT /materials/1/suppliers": error(422, "These suppliers do not exist or are inactive: [4]"),
    });
    open("/materials/1/suppliers");
    await userEvent.click(await screen.findByLabelText("Approve S01"));
    expect(screen.getByLabelText("Prefer S02")).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Save suppliers" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("inactive");
  });

  it("shows procurement only the linked suppliers, read-only", async () => {
    const beta = { ...ACME, id: 4, code: "S02", name: "Beta" };
    fakeServer({
      "GET /auth/me": { body: BUYER },
      "GET /materials/1": { body: STEEL },
      "GET /suppliers?active_only=true": { body: [ACME, beta] },
      "GET /materials/1/suppliers": { body: [{ supplier: ACME, preferred: true }] },
    });
    open("/materials/1/suppliers");
    expect(await screen.findByRole("cell", { name: "S01 Acme" })).toBeInTheDocument();
    expect(screen.queryByText("S02 Beta")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save suppliers" })).not.toBeInTheDocument();
  });
});

describe("sales import", () => {
  const file = new File(["date,product_code,quantity\n"], "sales.csv", { type: "text/csv" });

  it("uploads a file and shows the summary and the error report", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: PLANNER },
      "POST /imports/sales": {
        body: {
          id: 9,
          filename: "sales.csv",
          imported: 100,
          updated: 2,
          rejected: 1,
          errors: [{ row: 5, field: "product_code", message: "Unknown product: NOPE" }],
        },
      },
    });
    open("/import");
    await userEvent.upload(await screen.findByLabelText("Sales file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Import summary: sales.csv")).toBeInTheDocument();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Unknown product: NOPE" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download the error report" })).toHaveAttribute(
      "href",
      "/api/imports/9/errors.csv",
    );
    const sent = server.calls.find((call) => call.key === "POST /imports/sales");
    expect(sent?.init.body).toBeInstanceOf(FormData);
  });

  it("hides the error report when nothing was rejected", async () => {
    fakeServer({
      "GET /auth/me": { body: PLANNER },
      "POST /imports/sales": {
        body: { id: 9, filename: "sales.csv", imported: 3, updated: 0, rejected: 0, errors: [] },
      },
    });
    open("/import");
    await userEvent.upload(await screen.findByLabelText("Sales file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText("Import summary: sales.csv")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /error report/ })).not.toBeInTheDocument();
  });

  it("says when only part of a long error list is shown", async () => {
    fakeServer({
      "GET /auth/me": { body: PLANNER },
      "POST /imports/sales": {
        body: {
          id: 9,
          filename: "sales.csv",
          imported: 0,
          updated: 0,
          rejected: 5,
          errors: [{ row: 2, field: "date", message: "Bad date" }],
        },
      },
    });
    open("/import");
    await userEvent.upload(await screen.findByLabelText("Sales file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByText(/first 1 of 5/)).toBeInTheDocument();
  });

  it("shows a rejected file's message", async () => {
    fakeServer({
      "GET /auth/me": { body: PLANNER },
      "POST /imports/sales": error(415, "Only .csv and .xlsx files are accepted"),
    });
    open("/import");
    await userEvent.upload(await screen.findByLabelText("Sales file"), file);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only .csv and .xlsx");
  });

  it("stops files over 10 MB before uploading", async () => {
    const server = fakeServer({ "GET /auth/me": { body: PLANNER } });
    open("/import");
    const big = new File(["x"], "big.csv");
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    await userEvent.upload(await screen.findByLabelText("Sales file"), big);
    await userEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("10 MB");
    expect(server.calls.map((call) => call.key)).toEqual(["GET /auth/me"]);
  });
});

describe("users", () => {
  it("lets an admin add a user", async () => {
    const server = fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /users": { body: [ADMIN] },
      "POST /users": { status: 201, body: BUYER },
    });
    open("/users");
    await userEvent.type(await screen.findByLabelText("Email"), BUYER.email);
    await userEvent.type(screen.getByLabelText("Temporary password"), "a-password");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "procurement_manager");
    await userEvent.click(screen.getByRole("button", { name: "Add user" }));
    await waitFor(() =>
      expect(server.bodyOf("POST /users")).toEqual({
        email: BUYER.email,
        password: "a-password",
        role: "procurement_manager",
      }),
    );
    expect(screen.getByLabelText("Email")).toHaveValue("");
  });

  it("shows a duplicate email error", async () => {
    fakeServer({
      "GET /auth/me": { body: ADMIN },
      "GET /users": { body: [ADMIN] },
      "POST /users": error(409, "This email is already in use"),
    });
    open("/users");
    await userEvent.type(await screen.findByLabelText("Email"), ADMIN.email);
    await userEvent.type(screen.getByLabelText("Temporary password"), "a-password");
    await userEvent.click(screen.getByRole("button", { name: "Add user" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already in use");
  });
});

describe("server problems", () => {
  it("explains when the server cannot be reached", async () => {
    fakeServer({ "GET /auth/me": { body: ADMIN } });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/auth/me") return new Response(JSON.stringify(ADMIN));
      throw new Error("offline");
    }));
    open("/products");
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be reached");
  });
});
