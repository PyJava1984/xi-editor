# Copyright 2016 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import json
from collections import deque


def print_err(err):
    sys.stderr.write("plugin err>> %s\n" % err)
    sys.stderr.flush()


class RpcPeer(object):
    '''
    This is a simple RPC peer with some limitations. It assumes a single-threaded
    execution model, and only allows one outgoing RPC at a time. Incoming RPC's
    are queued.

    Also, in the current implementation, errors are not handled.
    '''

    def __init__(self, handler, stdin=None, stdout=None):
        self.handler = handler
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.pending = deque()
        self.id_counter = 0
        self.done = False

    def normalize_encoding(self, text):
        if sys.version_info <= (2, 7):
            if isinstance(text, str):
                text = text.decode('utf-8', errors='ignore')
        else:
            if isinstance(text, bytes):
                text = text.decode('utf-8', errors='ignore')

        return text

    def mainloop(self, waiting_for=None):
        while not self.done:
            line = self.stdin.readline()
            if len(line) == 0:
                self.done = True
                return None
            line = self.normalize_encoding(line)
            data = json.loads(line)
            if waiting_for is not None:
                print_err("waiting for {}".format(waiting_for))
            # 'id' is unique required field in response objects
            if waiting_for is not None and 'id' in data:
                if data['id'] != waiting_for:
                    raise Exception('waiting for {}, got {}'.format(
                        waiting_for, data['id']))
                try:
                    return data['result']
                except KeyError as err:
                    print_err("key error in mainloop: {}".format(err))
                    return None
            self.pending.append(data)
            if waiting_for is None:
                while self.has_pending():
                    self.handle(self.pending.popleft())

    def handle(self, data):
        req_id = data.get('id', None)
        method = data['method']
        params = data['params']
        result = self.handler(method, params, self)

        if result is not None:
            if req_id is None:
                raise Exception('unexpected return value on method ' + method)
            if hasattr(result, 'to_dict'):
                result = result.to_dict()
            resp = {'result': result, 'id': req_id}
            self.send(resp)
        elif req_id is not None:
            raise Exception('expected return value on method ' + method + ' id ' + str(id))

    def send(self, data):
        self.stdout.write(json.dumps(data))
        self.stdout.write('\n')
        self.stdout.flush()

    def send_rpc(self, method, params, req_id=None):
        req = {'method': method, 'params': params}
        if req_id is not None:
            req['id'] = req_id
        self.send(req)

    def send_rpc_sync(self, method, params):
        req_id = self.id_counter
        self.id_counter += 1
        self.send_rpc(method, params, req_id)
        return self.mainloop(waiting_for=req_id)

    def has_pending(self):
        return len(self.pending) != 0
