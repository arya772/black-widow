"""
*********************************************************************************
*                                                                               *
* parsing.py -- Classes and methods to parse an HTML or a full website.         *
*                                                                               *
********************** IMPORTANT BLACK-WIDOW LICENSE TERMS **********************
*                                                                               *
* This file is part of black-widow.                                             *
*                                                                               *
* black-widow is free software: you can redistribute it and/or modify           *
* it under the terms of the GNU General Public License as published by          *
* the Free Software Foundation, either version 3 of the License, or             *
* (at your option) any later version.                                           *
*                                                                               *
* black-widow is distributed in the hope that it will be useful,                *
* but WITHOUT ANY WARRANTY; without even the implied warranty of                *
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                 *
* GNU General Public License for more details.                                  *
*                                                                               *
* You should have received a copy of the GNU General Public License             *
* along with black-widow.  If not, see <http://www.gnu.org/licenses/>.          *
*                                                                               *
*********************************************************************************
"""

from abc import ABC
from html.parser import HTMLParser
from urllib.parse import urlparse

from tidylib import tidy_document
from app.utils.requests import request, Type as RequestType
from app.utils.helpers.logger import Log
from app.utils.helpers.validators import is_url
from app.utils.helpers.util import is_listable


# Black Widow HTML Parser
class Parser(HTMLParser, ABC):
    # Tags rilevanti
    relevant_tags = {
        'a': ['href'],  # { 'href': 'https://...' }
        'form': ['id', 'action', 'method'],
        # { 'action': 'https://...', 'method': 'GET', 'inputs': {'name': ['attr1', 'attr2']} }
        'input': [
            'id', 'name', 'type',
            'min', 'max',
            'required',
            'minlength',
            'maxlength',
            'pattern',
            'value'
        ],
        'textarea': [
            'id', 'name',
            'required',
            'minlength',
            'maxlength'
        ],
        'script': ['src', 'data', 'type'],  # { 'src': '/some/script.js', 'data': 'function() ...' }
        'link': ['href'],  # { 'href': '*.xml' }
        'html': [],
        'body': []
    }

    # Attributi contenenti url
    url_attrs = ['href', 'src', 'action']

    # Tag non chiuse (ignorare handle_endtag)
    not_closed_tags = ['input', 'link', 'meta', 'hr', 'img']

    def __init__(self, relevant=False):
        HTMLParser.__init__(self)
        self.tags = {}
        self.relevant = relevant
        self.queue_tag_ignored = []
        self.queue_tag = []
        self.queue_form = []
        self.url = None
        self.base_url = None
        self.url_scheme = ''

    # inserisce la tag passata per argomento, dentro l'ultima della coda
    # @param tag_dict Un dizionario contenente una parsed tag
    # @return void
    def __nest_tag__(self, tag_dict):
        # tag = tag_dict.get('tag')
        queue_tag_len = len(self.queue_tag)
        if queue_tag_len == 0:
            parent = self.tags
        else:
            parent = self.queue_tag[-1]
        parent_children = parent.get('children')
        if parent_children is None:
            parent_children = []
        parent_children.append(tag_dict)
        parent['children'] = parent_children
        if queue_tag_len == 0:
            self.tags = parent
        else:
            self.queue_tag[-1] = parent

    # Handler inizio tag
    # @param tag str La tag di apertura
    # @param attrs list[tuple{2}] Gli attributi della tag
    # @return void
    def handle_starttag(self, tag, attrs):
        tag = str(tag).lower()
        if (not self.relevant) or tag in Parser.relevant_tags.keys():
            tag_attrs = {}
            for attr in attrs:
                attr_key = str(attr[0]).lower()
                attr_value = str(attr[1])
                if (not self.relevant) or attr_key in Parser.relevant_tags.get(tag):
                    if self.base_url is not None and attr_key in Parser.url_attrs and (not is_url(attr_value)):
                        if attr_value[0:2] == '//':
                            attr_value = self.url_scheme + ':' + attr_value
                        else:
                            if attr_value[0:1] != '/':
                                attr_value = '/' + attr_value
                            attr_value = self.base_url + attr_value
                    tag_attrs[attr_key] = attr_value
            cur_tag = {'tag': tag, 'attrs': tag_attrs}
            self.queue_tag.append(cur_tag)
            if tag in Parser.not_closed_tags:
                self.handle_endtag(tag)
        else:
            self.queue_tag_ignored.append(tag)

    # Handler chiusura tag
    # @param tag str La tag di chiusura
    # @return void
    def handle_endtag(self, tag):
        tag = str(tag).lower()
        if len(self.queue_tag_ignored) > 0 and tag == self.queue_tag_ignored[-1]:
            self.queue_tag_ignored.pop()
            return
        if len(self.queue_tag) == 0:
            return
        cur_tag = self.queue_tag.pop()
        self.__nest_tag__(cur_tag)
        # Controllo obsoleto e difettoso:
        # if (tag == cur_tag.get('tag')): self.__nest_tag__(cur_tag)
        # else: Log.error(tag+' != '+str(cur_tag.get('tag')))

    # Handler contenuto di tag
    # @param data str Il contenuto dell'ultima tag aperta
    # @return void
    def handle_data(self, data):
        if len(self.queue_tag) == 0:
            return
        cur_tag = self.queue_tag[-1]
        if (not self.relevant) or 'data' in Parser.relevant_tags.get(cur_tag.get('tag')):
            cur_tag['data'] = data
            self.queue_tag[-1] = cur_tag

    # Fa il parsing della risposta dell'url passato per argomento
    # @param url L'url del quale fare il parsing della risposta
    # @param html L'html di cui ottenere il parsing
    # @return (dict, str) Html parsed and request cookies
    def parse(self, url=None, html=None):
        self.url = None
        self.base_url = None
        cookies = ''
        if url is not None:
            self.url = url
            url_parsed = urlparse(url)
            self.url_scheme = str(url_parsed.scheme)
            self.base_url = self.url_scheme + '://' + str(url_parsed.netloc)
            r = request(url, RequestType.GET)
            if r is None:
                return None
            try:
                html = r.json()
                Log.warning('Trying to parse a json with HTML parser!')
            except ValueError:
                html = r.text
            if r.headers is not None:
                for k in r.headers.keys():
                    if k == 'Set-Cookie' or k == 'set-cookie' or k == 'Set-cookie':
                        cookies = r.headers.get('Set-Cookie')
                        break
        # Sort html (and fix errors)
        sorted_html, errors = tidy_document(html)
        self.feed(sorted_html)
        return self.tags, cookies


# Esegue un parsing di un url/html
# @param url str L'url di cui fare il parsing (o None)
# @param html str La stringa html di cui fare il parsing (o None)
# @param bool relevant True se salvare solo tag rilevanti, False altrimenti
# @return dict, str Un html parsed e i cookies
def __parse__(url, html, relevant):
    parser = Parser(relevant)
    return parser.parse(url, html)


# Esegue un parsing di tutte le tag
# @param url str L'url di cui fare il parsing (o None)
# @param html str La stringa html di cui fare il parsing (o None)
# @return (dict, str) Un html parsed e i cookies
def parse(url=None, html=None):
    return __parse__(url, html, False)


# Esegue un parsing solo delle tag rilevanti
# @param url str L'url di cui fare il parsing (o None)
# @param html str La stringa html di cui fare il parsing (o None)
# @return (dict, str) Un html parsed e i cookies
def relevant_parse(url=None, html=None):
    return __parse__(url, html, True)


# Esegue un parsing solo delle tag attinenti a form (form, input, textarea)
# @param url str L'url di cui fare il parsing (o None)
# @param html str La stringa html di cui fare il parsing (o None)
# @return dict Un html parsed
def form_parse(url=None, html=None):
    parsed_html, cookies = relevant_parse(url, html)
    return find_forms(parsed_html, url), cookies


# cerca degli input dentro ad un parsed html (dict)
# @param dict parsed un html parsed
# @return dict {'input[name]': {'attr1': 'attr1_val' ...}}
def find_inputs(parsed):
    inputs = {}
    if parsed is None:
        return inputs
    if type(parsed) == dict:
        tag = parsed.get('tag')
        if tag in ('input', 'textarea'):
            attrs = parsed.get('attrs')
            form_input = {'tag': tag}
            for key, value in attrs.items():
                form_input[key] = value
            inputs[attrs.get('name')] = form_input
        inputs.update(find_inputs(parsed.get('children')))
    elif type(parsed) == list:
        for value in parsed:
            inputs.update(find_inputs(value))
    else:
        Log.error(str(parsed) + ' is not a valid parsed content!')
    return inputs


# Cerca i form dentro un parsed html (dict)
# @param parsed dict un html parsed
# @param url L'url in cui si trova il form
# @return list Lista form dentro l'html parsed
def find_forms(parsed, url=None):
    forms = []
    if parsed is None:
        return forms
    if type(parsed) == dict:
        if 'form' == parsed.get('tag'):
            attrs = parsed.get('attrs')
            action = attrs.get('action')
            method = attrs.get('method')
            if action is None:
                action = url
            if method is None:
                method = RequestType.POST
            form = {
                'method': method,
                'action': action,
                'inputs': find_inputs(parsed.get('children'))
            }
            forms.append(form)
        forms += find_forms(parsed.get('children'), url)
    elif type(parsed) == list:
        for value in parsed:
            forms += find_forms(value, url)
    else:
        Log.error(str(parsed) + ' is not a valid parsed content!')
    return forms


# Cerca i links dentro un parsed html (dict)
# @param parsed dict un html parsed
# @param url L'url in cui si trova il form
# @return set Lista links dentro l'html parsed
def find_links(parsed):
    links = set()
    if parsed is None:
        return links
    if type(parsed) == dict:
        attrs = parsed.get('attrs')
        if attrs is not None:
            url = None
            if 'form' == parsed.get('tag'):
                url = attrs.get('action')
            elif 'a' == parsed.get('tag'):
                url = attrs.get('href')
            if url is not None:
                links.add(url)
        links = links.union(find_links(parsed.get('children')))
    elif type(parsed) == list:
        for value in parsed:
            links = links.union(find_links(value))
    else:
        Log.error(str(parsed) + ' is not a valid parsed content!')
    return links


# Printa il risultato delle funzioni @parse e @relevant_parse
# @param parsed dict un html parsed
# @param depth Attuale profondità
# @return void
def print_parsed(parsed, depth=0):
    space = ' ' * depth
    if type(parsed) == dict:
        print(space + '{')
        for key, value in parsed.items():
            if key == 'children':
                print_parsed(value, depth + 1)
            elif is_listable(value):
                print((space + '  ') + str(key) + ':')
                print_parsed(value, depth + 2)
                # print((space+'  ') + str(key) + ':')
                # subspace = ' ' * (depth+1)
                # for el in dict:
                #  if (is_listable(el)):
            else:
                print((space + '  ') + str(key) + ': ' + str(value))
        print(space + '}')
    elif type(parsed) == list:
        for value in parsed:
            print_parsed(value, depth + 1)
    else:
        Log.error(str(parsed) + ' is not a valid parsed content!')
