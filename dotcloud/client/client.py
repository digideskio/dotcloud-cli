import requests
import json
import sys
import os
import httplib

from .auth import BasicAuth, OAuth2Auth, NullAuth
from .response import *
from .errors import RESTAPIError, AuthenticationNotConfigured

httplib.HTTPConnection.debuglevel = 1

class RESTClient(object):
    def __init__(self, endpoint='https://rest.dotcloud.com/v1',
            debug=False, user_agent=None, version_checker=None):
        self.endpoint = endpoint
        self.debug = debug
        self.authenticator = NullAuth()
        self._make_session()
        self._user_agent = user_agent
        self._version_checker = version_checker

    def make_prefix_client(self, prefix=''):
        subclient = RESTClient(
                endpoint='{endpoint}{prefix}'.format(
                    endpoint=self.endpoint, prefix=prefix),
                debug=self.debug, user_agent=self._user_agent,
                version_checker=self._version_checker)
        subclient.session = self.session
        return subclient

    def _make_session(self):
        headers = {'Accept': 'application/json'}
        hooks = {
            'args': lambda args: self.authenticator.args_hook(args),
            'pre_request': self._pre_request_hook,
            'response': self._response_hook
        }
        self.session = requests.session(headers=headers, hooks=hooks,
            verify=True)

    def _pre_request_hook(self, request):
        if self._user_agent:
            request.headers['User-Agent'] = self._user_agent
        r = self.authenticator.pre_request_hook(request)
        if self.debug:
            print >>sys.stderr, '### {method} {url} data={data}'.format(
                method  = request.method,
                url     = request.path_url,
                data    = request.data
            )
        return r

    def _response_hook(self, response):
        r = self.authenticator.response_hook(response)
        if self.debug:
            print >>sys.stderr, '### {code} TraceID:{trace_id}'.format(
                code=response.status_code,
                trace_id=response.headers['X-DotCloud-TraceID'])
        return r

    def build_url(self, path):
        if path == '' or path.startswith('/'):
            return self.endpoint + path
        else:
            return path

    def get(self, path='', streaming=False):
        return self.make_response(self.session.get(self.build_url(path),
            prefetch=not streaming, timeout=180), streaming)

    def post(self, path='', payload={}):
        return self.make_response(
            self.session.post(self.build_url(path), data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}, timeout=180))

    def put(self, path='', payload={}):
        return self.make_response(
            self.session.put(self.build_url(path),
                data=json.dumps(payload), timeout=180,
                headers={'Content-Type': 'application/json'}))

    def delete(self, path=''):
        return self.make_response(
            self.session.delete(self.build_url(path), timeout=180,
                headers={'Content-Length': '0'}))

    def patch(self, path='', payload={}):
        return self.make_response(
            self.session.patch(self.build_url(path), timeout=180,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}))

    def make_response(self, res, streaming=False):
        trace_id = res.headers.get('X-DotCloud-TraceID')
        if res.headers['Content-Type'] == 'application/json':
            pass
        elif res.status_code == requests.codes.no_content:
            return BaseResponse.create(res=res, trace_id=trace_id)
        else:
            raise RESTAPIError(code=requests.codes.server_error,
                               desc='Server responded with unsupported ' \
                                'media type: {0} (status: {1})' \
                                .format(res.headers['Content-Type'],
                                    res.status_code),
                               trace_id=trace_id)

        if res.status_code == requests.codes.im_a_teapot:
            # Maintenance mode
            message = 'The API is currently in maintenance mode.\n'\
            'Please try again later and check http://status.dotcloud.com '\
            'for more information.'
            if res.json['error']['description'] is not None:
                message = res.json['error']['description']
            raise RESTAPIError(code=requests.codes.im_a_teapot, desc=message)

        if not res.ok:
            data = json.loads(res.text)
            raise RESTAPIError(code=res.status_code,
                desc=data['error']['description'], trace_id=trace_id)

        if self._version_checker:
            self._version_checker(res.headers.get('X-DOTCLOUD-CLI-VERSION-MIN'),
                    res.headers.get('X-DOTCLOUD-CLI-VERSION-CUR'))

        return BaseResponse.create(res=res, trace_id=trace_id,
                streaming=streaming)
