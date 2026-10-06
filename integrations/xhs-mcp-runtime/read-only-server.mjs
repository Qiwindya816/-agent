#!/usr/bin/env node

/**
 * TravelMind's read-only HTTP wrapper for @sillyl12324/xhs-mcp.
 *
 * The upstream server exposes publishing and interaction tools as well as
 * retrieval tools. TravelMind deliberately registers only authentication,
 * search, and note-detail operations so the knowledge-base crawler cannot
 * publish, like, collect, comment, follow, or delete platform content.
 */

import http from "node:http";
import fs from "node:fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";
import { chromium } from "playwright";
import {
  accountTools,
  handleAccountTools,
} from "@sillyl12324/xhs-mcp/dist/tools/account.js";
import {
  authTools,
  handleAuthTools,
} from "@sillyl12324/xhs-mcp/dist/tools/auth.js";
import {
  contentTools,
  handleContentTools,
} from "@sillyl12324/xhs-mcp/dist/tools/content.js";
import { initDatabase } from "@sillyl12324/xhs-mcp/dist/db/index.js";
import { getAccountPool } from "@sillyl12324/xhs-mcp/dist/core/account-pool.js";

const PORT = Number.parseInt(process.env.XHS_MCP_PORT || "18060", 10);
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const ALLOWED_NAMES = new Set([
  "xhs_list_accounts",
  "xhs_add_account",
  "xhs_check_login_session",
  "xhs_submit_verification",
  "xhs_check_auth_status",
  "xhs_search",
  "xhs_get_note",
]);

const allowedAccountTools = accountTools.filter((tool) => ALLOWED_NAMES.has(tool.name));
const allowedAuthTools = authTools.filter((tool) => ALLOWED_NAMES.has(tool.name));
const allowedContentTools = contentTools.filter((tool) => ALLOWED_NAMES.has(tool.name));
const allowedTools = [...allowedAccountTools, ...allowedAuthTools, ...allowedContentTools];

function detectBrowserExecutable() {
  const configured = process.env.XHS_MCP_BROWSER_EXECUTABLE;
  const candidates = process.platform === "win32"
    ? [
        configured,
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
      ]
    : [configured, "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"];
  return candidates.find((candidate) => candidate && fs.existsSync(candidate));
}

// Reuse an installed Chrome/Edge. This avoids downloading Playwright's large
// browser bundle and leaves the user's existing frontend Node setup untouched.
const browserExecutable = detectBrowserExecutable();
if (browserExecutable) {
  const originalLaunch = chromium.launch.bind(chromium);
  chromium.launch = (options = {}) => originalLaunch({ ...options, executablePath: browserExecutable });
}

function createReadOnlyMcpServer(pool, db) {
  const server = new Server(
    { name: "travelmind-xhs-readonly", version: "1.0.0" },
    { capabilities: { tools: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: allowedTools }));
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args = {} } = request.params;
    if (!ALLOWED_NAMES.has(name)) {
      throw new McpError(ErrorCode.MethodNotFound, `Tool is not allowed: ${name}`);
    }
    if (allowedAccountTools.some((tool) => tool.name === name)) {
      return handleAccountTools(name, args, pool, db);
    }
    if (allowedAuthTools.some((tool) => tool.name === name)) {
      return handleAuthTools(name, args, pool, db);
    }
    if (allowedContentTools.some((tool) => tool.name === name)) {
      return handleContentTools(name, args, pool, db);
    }
    throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
  });
  return server;
}

function sendJson(response, status, payload) {
  response.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Expose-Headers": "Mcp-Session-Id",
    "Content-Type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new Error("Request body is too large");
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

const db = await initDatabase();
const pool = getAccountPool(db);

const httpServer = http.createServer(async (request, response) => {
  const path = new URL(request.url || "/", `http://${request.headers.host || "127.0.0.1"}`).pathname;
  if (request.method === "OPTIONS") {
    response.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "content-type, mcp-session-id",
      "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    });
    response.end();
    return;
  }
  if (request.method === "GET" && path === "/health") {
    sendJson(response, 200, {
      status: "ok",
      server: "travelmind-xhs-readonly",
      browser: browserExecutable ? "system" : "playwright-managed",
      toolCount: allowedTools.length,
    });
    return;
  }
  if (request.method !== "POST" || path !== "/mcp") {
    sendJson(response, 404, { error: "Not found" });
    return;
  }

  let server;
  let transport;
  try {
    const body = await readJson(request);
    transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    server = createReadOnlyMcpServer(pool, db);
    await server.connect(transport);
    await transport.handleRequest(request, response, body);
  } catch (error) {
    if (!response.headersSent) {
      sendJson(response, 500, {
        jsonrpc: "2.0",
        error: { code: -32603, message: error instanceof Error ? error.message : String(error) },
        id: null,
      });
    } else if (!response.writableEnded) {
      response.end();
    }
  } finally {
    await transport?.close().catch(() => {});
    await server?.close().catch(() => {});
  }
});

async function shutdown() {
  httpServer.close();
  await pool.closeAll();
  db.close();
}

process.on("SIGINT", async () => {
  await shutdown();
  process.exit(0);
});
process.on("SIGTERM", async () => {
  await shutdown();
  process.exit(0);
});

httpServer.listen(PORT, "127.0.0.1", () => {
  console.error(`TravelMind Xiaohongshu MCP: http://127.0.0.1:${PORT}/mcp`);
  console.error(`Read-only tools: ${[...ALLOWED_NAMES].join(", ")}`);
});
