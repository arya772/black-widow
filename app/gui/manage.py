"""
*********************************************************************************
*                                                                               *
* manage.py -- Django manager.                                                  *
*                                                                               *
* Methods to use the Django manager to test the web server                      *
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

import os
import sys

from gunicorn.app.wsgiapp import run as gunicorn_run
from django.core import management

from app.env_local import APP_WEB_HOST, APP_WEB_PORT
from app.env import EXEC_PATH, APP_NAME
from app.utils.helpers.logger import Log
from app.utils.helpers.network import get_ip_address
from app.gui.web.wsgi import WEB_PACKAGE


def _get_bind_socket():
    host = APP_WEB_HOST
    if host is None:
        host = get_ip_address()
    if host is None:
        host = '0.0.0.0'
    return str(host) + ':' + str(APP_WEB_PORT)


def django_gui():
    sys.path.insert(0, os.path.dirname(__file__))
    bind_host = _get_bind_socket()
    Log.info("Starting " + str(APP_NAME) + ' GUI')
    sys.argv = [sys.argv[0], 'web.wsgi', '-b', bind_host]
    gunicorn_run()


def django_cmd(args):
    # Go to "web" directory
    if 'runserver' not in args:
        os.chdir(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'web'))
    elif len(args) <= 1:
        bind_host = _get_bind_socket()
        args.append(bind_host)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", WEB_PACKAGE + ".settings")
    management.execute_from_command_line([EXEC_PATH + ' --django', ] + args)
