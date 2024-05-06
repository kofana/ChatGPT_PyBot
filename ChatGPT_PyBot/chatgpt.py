import sys
import cmd
import requests
import json
import os
import uuid
from rich.console import Console
from rich.markdown import Markdown
#from OpenAIAuth.OpenAIAuth import OpenAIAuth, Debugger
from OpenAIAuth import Auth0 as OpenAIAuth


console = Console()
BASE_URL = "https://chat.openai.com/"

def generate_uuid() -> str:
    uid = str(uuid.uuid4())
    return uid



class Debugger:
    def __init__(self, debug: bool = False):
        if debug:
            print("Debugger enabled on OpenAIAuth")
        self.debug = debug

    def set_debug(self, debug: bool):
        self.debug = debug

    def log(self, message: str, end: str = "\n"):
        if self.debug:
            print(message, end=end)


class ChatBot:

    config: json
    conversation_id: str
    parent_id: str
    headers: dict
    conversation_id_prev: str
    parent_id_prev: str

    def __init__(self, config, conversation_id=None, debug=False, refresh=True) -> Exception:
        self.debugger = Debugger(debug)
        self.debug = debug
        self.config = config
        self.conversation_id = conversation_id
        self.parent_id = generate_uuid()
        if "session_token" in config or ("email" in config and "password" in config) and refresh:
            self.refresh_session()
        if "Authorization" in config:
            self.refresh_headers()

    # Resets the conversation ID and parent ID
    def reset_chat(self) -> None:
        self.conversation_id = None
        self.parent_id = generate_uuid()

    def refresh_headers(self) -> None:
        if "Authorization" not in self.config:
            self.config["Authorization"] = ""
        elif self.config["Authorization"] is None:
            self.config["Authorization"] = ""
        self.headers = {
            "Host": "chat.openai.com",
            "Accept": "text/event-stream",
            "Authorization": "Bearer " + self.config["Authorization"],
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/16.1 Safari/605.1.15",
            "X-Openai-Assistant-App-Id": "",
            "Connection": "close",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://chat.openai.com/chat",
        }

    def get_chat_stream(self, data) -> None:
        response = requests.post(
            BASE_URL+"backend-api/conversation",
            headers=self.headers,
            data=json.dumps(data),
            stream=True,
            timeout=100,
        )
        for line in response.iter_lines():
            try:
                line = line.decode("utf-8")
                if line == "":
                    continue
                line = line[6:]
                line = json.loads(line)
                try:
                    message = line["message"]["content"]["parts"][0]
                    self.conversation_id = line["conversation_id"]
                    self.parent_id = line["message"]["id"]
                except:
                    continue
                yield {
                    "message": message,
                    "conversation_id": self.conversation_id,
                    "parent_id": self.parent_id,
                }
            except:
                continue

    # Gets the chat response as text -- Internal use only
    def get_chat_text(self, data) -> dict:
        # Create request session
        s = requests.Session()
        # set headers
        s.headers = self.headers
        # Set multiple cookies
        if "session_token" in self.config:
            s.cookies.set(
                "__Secure-next-auth.session-token",
                self.config["session_token"],
            )
        s.cookies.set(
            "__Secure-next-auth.callback-url",
            "https://chat.openai.com/",
        )
        # Set proxies
        if self.config.get("proxy", "") != "":
            s.proxies = {
                "http": self.config["proxy"],
                "https": self.config["proxy"],
            }
        response = s.post(
            BASE_URL+"backend-api/conversation",
            data=json.dumps(data),
        )
        try:
            response = response.text.splitlines()[-4]
            response = response[6:]
        except Exception as exc:
            self.debugger.log("Incorrect response from OpenAI API")
            try:
                resp = response.json()
                self.debugger.log(resp)
                if resp['detail']['code'] == "invalid_api_key" or resp['detail']['code'] == "token_expired":
                    if "email" in self.config and "password" in self.config:
                        self.refresh_session()
                        return self.get_chat_text(data)
                    else:
                        self.debugger.log("Missing necessary credentials")
                        raise Exception(
                            "Missing necessary credentials") from exc
            except Exception as exc2:
                raise Exception("Not a JSON response") from exc2
            raise Exception("Incorrect response from OpenAI API") from exc
        response = json.loads(response)
        self.parent_id = response["message"]["id"]
        self.conversation_id = response["conversation_id"]
        message = response["message"]["content"]["parts"][0]
        return {
            "message": message,
            "conversation_id": self.conversation_id,
            "parent_id": self.parent_id,
        }

    # Gets the chat response
    def get_chat_response(self, prompt, output="text") -> dict or None:
        data = {
            "action": "next",
            "messages": [
                {
                    "id": str(generate_uuid()),
                    "role": "user",
                    "content": {"content_type": "text", "parts": [prompt]},
                },
            ],
            "conversation_id": self.conversation_id,
            "parent_message_id": self.parent_id,
            "model": "text-davinci-002-render",
        }
        self.conversation_id_prev = self.conversation_id
        self.parent_id_prev = self.parent_id
        if output == "text":
            return self.get_chat_text(data)
        elif output == "stream":
            return self.get_chat_stream(data)
        else:
            raise ValueError("Output must be either 'text' or 'stream'")

    def rollback_conversation(self) -> None:
        self.conversation_id = self.conversation_id_prev
        self.parent_id = self.parent_id_prev

    def refresh_session(self) -> Exception:
        if (
            "session_token" not in self.config
            and ("email" not in self.config or "password" not in self.config)
            and "Authorization" not in self.config
        ):
            error = ValueError("No tokens provided")
            self.debugger.log(error)
            raise error
        elif "session_token" in self.config:
            if (
                self.config["session_token"] is None
                or self.config["session_token"] == ""
            ):
                raise ValueError("No tokens provided")
            s = requests.Session()
            if self.config.get("proxy", "") != "":
                s.proxies = {
                    "http": self.config["proxy"],
                    "https": self.config["proxy"],
                }
            # Set cookies
            s.cookies.set(
                "__Secure-next-auth.session-token",
                self.config["session_token"],
            )
            # s.cookies.set("__Secure-next-auth.csrf-token", self.config['csrf_token'])
            response = s.get(
                BASE_URL+"api/auth/session",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, "
                    "like Gecko) Version/16.1 Safari/605.1.15 ",
                },
            )
            if response.status_code != 200:
                self.debugger.log("Invalid status code")
                self.debugger.log(response.status_code)
                raise Exception("Wrong response code")
            try:
                self.config["session_token"] = response.cookies.get(
                    "__Secure-next-auth.session-token",
                )
                self.config["Authorization"] = response.json()["accessToken"]
                self.refresh_headers()
            except Exception as exc:
                print("Error refreshing session")
                self.debugger.log("Response: '" + str(response.text) + "'")
                self.debugger.log(response.status_code)
                # Check if response JSON is empty
                if response.json() == {}:
                    self.debugger.log("Empty response")
                    self.debugger.log("Probably invalid session token")
                    if 'email' in self.config and 'password' in self.config:
                        del self.config['session_token']
                        self.login(self.config['email'],
                                   self.config['password'])
                        return
                    else:
                        raise ValueError(
                            "No email and password provided") from exc
                raise Exception("Error refreshing session") from exc
        elif "email" in self.config and "password" in self.config:
            try:
                self.login(self.config["email"], self.config["password"])
            except Exception as exc:
                self.debugger.log("Login failed")
                raise exc
        elif "Authorization" in self.config:
            self.refresh_headers()
            return
        else:
            raise ValueError("No tokens provided")

    def login(self, email, password) -> None:
        self.debugger.log("Logging in...")
        use_proxy = False
        proxy = None
        if "proxy" in self.config:
            if self.config["proxy"] != "":
                use_proxy = True
                proxy = self.config["proxy"]
        auth = OpenAIAuth(email, password, use_proxy, proxy) #debug=self.debug)
        try:
            auth.begin()
        except Exception as exc:
            # if ValueError with e as "Captcha detected" fail
            if exc == "Captcha detected":
                self.debugger.log(
                    "Captcha not supported. Use session tokens instead.")
                raise ValueError("Captcha detected") from exc
            raise exc
        if auth.access_token is not None:
            self.config["Authorization"] = auth.access_token
            if auth.session_token is not None:
                self.config["session_token"] = auth.session_token
            else:
                possible_tokens = auth.session.cookies.get(
                    "__Secure-next-auth.session-token",
                )
                if possible_tokens is not None:
                    if len(possible_tokens) > 1:
                        self.config["session_token"] = possible_tokens[0]
                    else:
                        try:
                            self.config["session_token"] = possible_tokens
                        except Exception as exc:
                            raise Exception("Error logging in") from exc
            self.refresh_headers()
        else:
            raise Exception("Error logging in")


class GPTShell(cmd.Cmd):

    prompt = "You: "
    chatbot = None

    def _print_output(self, output):
        console.print(Markdown("ChatGPT: " + output),style="#BC9D41")
        print("")

    def do_clear(self, _):
        #Features to be perfected
        self._print_output('* Conversation cleared')

    def default(self, line):
        print("")
        print("ChatGPT is thinking,The response speed depends on your network and the complexity of the question,please don't hit enter again!")
        print("")

        response = self.chatbot.get_chat_response(line)["message"]
        self._print_output(response)

    def do_session(self, _):
        self.chatbot.refresh_session()
        self._print_output('* Session refreshed')

    def do_exit(self, _):
        sys.exit(0)

def main():

    file_list = os.listdir(os.getcwd())
    if 'config.json' not in file_list:
        print("config.json not found in current directory!")
        print("Please read the configuration instructions at https://github.com/liuhuanshuo/ChatGPT_PyBot")
        print("And make sure that config.json file is available in the current directory!")
        exit()

    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)
    if "--debug" in sys.argv:
        print("Debugging enabled.")
        debug = True
    else:
        debug = False

    help_tips = len(sys.argv) > 1 and (sys.argv[1] == "--help")
    if help_tips:
        print("To start ChatGPT, make sure to include the file config.json in the current directory!")
        exit()

    print("Logging in...")
    print("")
    try:
        chatbot = ChatBot(config, debug=debug)
    except:
        print("Error when logging in to OpenAI. Please check the configuration information in config.json is valid.")
        print("If you are using an account password for verification, make sure your terminal can access OpenAI, otherwise, use session_token!")
        print("More configuration instructions, please refer to https://github.com/liuhuanshuo/ChatGPT_PyBot!")
        exit()

    if len(sys.argv) > 1 and not help_tips:
        response = chatbot.get_chat_response(" ".join(sys.argv[1:]))["message"]
        console.print(Markdown("ChatGPT: " + response),style="#BC9D41")
        return

    shell = GPTShell()
    shell.chatbot = chatbot
    shell.cmdloop()

if __name__ == '__main__':
    main()
