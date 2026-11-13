import json
import os
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PORT = int(os.environ.get("PORT", "8000"))
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def load_local_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


load_local_env()


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/api/ask":
            self.send_error(404, "Not found")
            return

        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            self.send_json(503, {"error": "DEEPSEEK_API_KEY is not configured on the server."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            question = str(payload.get("question", "")).strip()
            context = payload.get("context", {})
            if not question:
                self.send_json(400, {"error": "Please enter a question."})
                return

            prompt = (
                "你是由 DeepSeek API 驱动的互动式经济资料仪表板分析助手。若用户询问你是否基于 DeepSeek，必须明确回答：是的，本地后端正在调用 DeepSeek API；不要否认或模糊这一点。请使用简体中文回答用户问题，"
                "只根據提供的資料，不要捏造不存在的數字。回答最高、最低或排名问题时，必须先筛选对应年份并逐项比较后再给结论，不能先猜测再修改。"
                "不要输出 Markdown 粗体符号（**）或标题符号（#）。若资料不足，请清楚说明限制。"
                f"\n目前儀表板資料摘要：{json.dumps(context, ensure_ascii=False)}"
                f"\n使用者問題：{question}"
            )
            request = Request(
                DEEPSEEK_URL,
                data=json.dumps({
                    "model": "deepseek-chat",
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                }).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urlopen(request, timeout=20) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = result.get("choices", [{}])[0].get("message", {}).get("content")
            if not answer:
                raise ValueError("DeepSeek returned no answer.")
            self.send_json(200, {"answer": answer})
        except (json.JSONDecodeError, ValueError) as error:
            self.send_json(400, {"error": str(error)})
        except HTTPError as error:
            try:
                upstream = error.read().decode("utf-8", errors="replace")
                details = json.loads(upstream).get("error", {}).get("message", "")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                details = ""
            message = f"DeepSeek API {error.code}"
            if details:
                message += f": {details}"
            self.send_json(502, {"error": message})
        except URLError as error:
            self.send_json(502, {"error": f"DeepSeek connection failed: {error.reason}"})
        except (TimeoutError, socket.timeout):
            self.send_json(504, {"error": "DeepSeek request timed out."})

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Serving HW5 dashboard at http://localhost:{PORT}")
    ThreadingHTTPServer(("localhost", PORT), Handler).serve_forever()
