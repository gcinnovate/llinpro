import json
from . import db, get_session
import web
from settings import config
from app.tools.utils import get_basic_auth_credentials, auth_user
from app.tools.utils import get_location_role_reporters, queue_schedule
import datetime


class LocationsEndpoint:
    def GET(self, district_code):
        params = web.input(from_date="", type="")
        web.header("Content-Type", "application/json; charset=utf-8")
        username, password = get_basic_auth_credentials()
        r = auth_user(db, username, password)
        if not r[0]:
            web.header('WWW-Authenticate', 'Basic realm="Auth API"')
            web.ctx.status = '401 Unauthorized'
            return json.dumps({'detail': 'Authentication failed!'})

        y = db.query("SELECT id, lft, rght FROM locations WHERE code = $code", {'code': district_code})
        location_id = 0
        if y:
            loc = y[0]
            location_id = loc['id']
            lft = loc['lft']
            rght = loc['rght']
        SQL = (
            "SELECT a.id, a.name, a.code, a.uuid, a.lft, a.rght, a.tree_id, a.tree_parent_id, "
            "b.code as parent_code, c.level, c.name as type, "
            "to_char(a.cdate, 'YYYY-mm-dd') as created "
            " FROM locations a, locations b, locationtype c"
            " WHERE "
            " a.tree_parent_id = b.id "
            " AND a.lft > %s AND a.lft < %s "
            " AND a.type_id = c.id "
        )
        SQL = SQL % (lft, rght)
        if params.from_date:
            SQL += " AND a.cdate >= $date "
        if params.type:
            SQL += " AND c.name = $type "
        r = db.query(SQL, {'id': location_id, 'date': params.from_date, 'type': params.type})
        ret = []
        for i in r:
            ret.append(dict(i))
        return json.dumps(ret)


class LocationsCSVEndpoint:
    def GET(self):
        # params = web.input()
        username, password = get_basic_auth_credentials()
        r = auth_user(db, username, password)
        if not r[0]:
            web.header("Content-Type", "application/json; charset=utf-8")
            web.header('WWW-Authenticate', 'Basic realm="Auth API"')
            web.ctx.status = '401 Unauthorized'
            return json.dumps({'detail': 'Authentication failed!'})
        web.header("Content-Type", "application/zip; charset=utf-8")
        web.seeother("/static/downloads/llin.csv.zip")


class ReportersXLEndpoint:
    def GET(self):
        username, password = get_basic_auth_credentials()
        r = auth_user(db, username, password)
        if not r[0]:
            web.header("Content-Type", "application/json; charset=utf-8")
            web.header('WWW-Authenticate', 'Basic realm="Auth API"')
            web.ctx.status = '401 Unauthorized'
            return json.dumps({'detail': 'Authentication failed!'})
        web.header("Content-Type", "application/zip; charset=utf-8")
        # web.header('Content-disposition', 'attachment; filename=%s.csv'%file_name)
        web.seeother("/static/downloads/reporters_all.xls.zip")


class DispatchSMS:
    def GET(self, id):
        web.header("Content-Type", "application/json; charset=utf-8")
        r = db.query(
            "SELECT waybill, destination_id, quantity_bales FROM distribution_log_w2sc_view "
            "WHERE id = $id", {'id': id})
        if r:
            res = r[0]
            msg = "Please send 'REC %s %s' to %s if you received %s bales of nets with waybill %s."
            to_subcounty = res['destination_id']
            msg = msg % (
                res['waybill'], res['quantity_bales'],
                config.get('shortcode', '6400'),
                res['quantity_bales'], res['waybill'])
            ret = {'sms': msg, 'to_subcounty': to_subcounty}
            return json.dumps(ret)

    def POST(self, id):
        params = web.input(to_subcounty="", sms="")
        print "XXXXXXXXXX", params.to_subcounty, params.sms
        session = get_session()
        subcounty_reporters = get_location_role_reporters(
            db, params.to_subcounty, config['subcounty_reporters'])
        if not subcounty_reporters:
            return "<h4>No reporters</h4>"
        sms_params = {'text': params.sms, 'to': ' '.join(subcounty_reporters)}
        current_time = datetime.datetime.now()
        sched_time = current_time + datetime.timedelta(minutes=1)
        queue_schedule(db, sms_params, sched_time, session.sesid)
        return "<h4>Successfully sent notification SMS</h4>"
