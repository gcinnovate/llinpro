import json
from . import db, get_session, require_login
import web
from settings import config
from app.tools.utils import get_basic_auth_credentials, auth_user, get_webhook_msg
from app.tools.utils import get_location_role_reporters, queue_schedule
import datetime
from StringIO import StringIO
import csv


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
            msg = 'Please send "REC %s %s" to %s if you received %s bales of nets with waybill %s.'
            to_subcounty = res['destination_id']
            msg = msg % (
                res['waybill'], res['quantity_bales'],
                config.get('shortcode', '6400'),
                res['quantity_bales'], res['waybill'])
            ret = {"sms": msg, "to_subcounty": to_subcounty}
            return json.dumps(ret)

    def POST(self, id):
        params = web.input(to_subcounty="", sms="")
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


class DispatchSummary:
    @require_login
    def GET(self):
        r = db.query(
            "SELECT district, destination subcounty, sum(quantity_bales) total_bales "
            "FROM distribution_log_w2sc_view "
            "GROUP by district, destination "
            "ORDER by district, subcounty")
        csv_file = StringIO()
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['District', 'SubCounty', 'Total Bales'])
        for i in r:
            csv_writer.writerow([i['district'], i['subcounty'], i['total_bales']])
        web.header('Content-Type', 'text/csv')
        web.header('Content-disposition', 'attachment; filename=SubcountyDispatchSummary.csv')
        return csv_file.getvalue()


class DistrictDispatchSummary:
    @require_login
    def GET(self):
        r = db.query(
            "SELECT district, sum(quantity_bales) total_bales "
            "FROM distribution_log_w2sc_view "
            "GROUP by district "
            "ORDER by district")
        csv_file = StringIO()
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(['District', 'Total Bales'])
        for i in r:
            csv_writer.writerow([i['district'], i['total_bales']])
        web.header('Content-Type', 'text/csv')
        web.header('Content-disposition', 'attachment; filename=DistrictDispatchSummary.csv')
        return csv_file.getvalue()


class Remarks:
    def POST(self):
        web.header("Content-Type", "application/json; charset=utf-8")
        params = web.input()
        remark = get_webhook_msg(params, 'msg')
        phone = params.phone.replace('+', '')
        with db.transaction():
            r = db.query(
                "SELECT id, reporting_location, district_id, "
                "district, loc_name "
                "FROM reporters_view4 WHERE replace(telephone, '+', '') = $tel "
                "OR replace(alternate_tel, '+', '') = $tel LIMIT 1", {'tel': phone})
            if r:
                reporter = r[0]
                db.query(
                    "INSERT INTO alerts(district_id, reporting_location, alert) "
                    "VALUES($district_id, $loc, $msg) ",
                    {
                        'district_id': reporter['district_id'],
                        'loc': reporter['reporting_location'],
                        'msg': remark})
            else:
                db.query(
                    "INSERT INTO alerts (alert) VALUES($msg)", {'msg': remark})
            ret = ("Thank you for your report, this report will be sent to relevant authorities.")
            return json.dumps({"message": ret})


class DistrictStats:
    def GET(self):
        # web.header("Content-Type", "application/json; charset=utf-8")
        params = web.input(field="color")
        field = params.field
        rs = db.query(
            "SELECT upper(district) district, total_bales, coverage, color, total_subcounties "
            "FROM district_stats_view ORDER by district")
        ret = {}
        for r in rs:
            if field == 'coverage':
                val = (
                    "<strong>District:</strong> %(district)s<br/>"
                    "<strong>Total Sub-Counties:</strong> %(total_subcounties)s<br/>"
                    "<strong>Coverage:</strong> %(coverage)s%%<br/>"
                    "<strong>Bales Distributed:</strong> %(total_bales)s" % (r))
                ret[r['district']] = val
            else:
                ret[r['district']] = r[field]
        return json.dumps(ret)


class KannelSeries:
    def GET(self):
        params = web.input(id="")
        if params.id:
            rs = db.query(
                "SELECT * FROM sms_stats WHERE id = $id", {'id': params.id})
            ret = ""
            if rs:
                r = rs[0]
                # period = "For %s (Last updated: %s)" % (r['month'], r['updated'])
                incoming = "Incoming,%s,%s,%s,%s" % (r['mtn_in'], r['airtel_in'], r['africel_in'], r['utl_in'])
                outgoing = "Outgoing,%s,%s,%s,%s" % (r['mtn_out'], r['airtel_out'], r['africel_out'], r['utl_out'])
                # ret = period + "\n" + incoming + "\n" + outgoing
                ret = incoming + "\n" + outgoing
            return ret
        return ""


class ChartData:
    def GET(self):
        params = web.input(chart_type="", wave="")
        chart_type = params.chart_type
        wave = params.wave

        rs = db.query(
            "SELECT district, total_bales, coverage,  total_subcounties "
            "FROM district_stats_view "
            "WHERE district_id IN (SELECT district_id FROM wave_districts WHERE wave_id = $wave) "
            "ORDER by district", {'wave': wave})
        districts = []
        data = []
        for r in rs:
            districts.append(r['district'])
            data.append(r[chart_type])
        ret = ','.join(districts)
        ret += "\n"
        ret += ','.join(data)
        return ret


class FixDistributeVillageNets:
    """Fix:XXX Webhook issued when subcounty store managers distribute to the distribution points"""
    def POST(self):
        web.header("Content-Type", "application/json; charset=utf-8")
        params = web.input(waybill="", nets="", phone="")
        waybill = params.waybill
        nets = params.nets
        try:
            nets = int(float(nets))
        except:
            return json.dumps({"message": "The nets distributed must be a number"})

        phone = params.phone.replace('+', '')
        with db.transaction():
            r = db.query(
                "SELECT id, reporting_location, district_id FROM reporters WHERE replace(telephone, '+', '') = $tel "
                "OR replace(alternate_tel, '+', '') = $tel LIMIT 1", {'tel': phone})
            if r and waybill and nets:
                reporter = r[0]
                reporter_id = reporter['id']
                district_id = reporter['district_id']
                res = db.query(
                    "SELECT id FROM distribution_log_sc2dp_view WHERE waybill = $waybill AND "
                    "reporter_id = $reporter_id", {'waybill': waybill, 'reporter_id': reporter_id})
                if res:
                    # entry already exists
                    log_id = res[0]['id']
                    db.query(
                        "UPDATE distribution_log SET quantity_nets = $nets, updated = now() "
                        "WHERE id = $id", {'nets': nets, 'id': log_id})
                    ret = (
                        "Distribution with Delivery Note No.: %s already recorded by you. "
                        " %s nets have been recorded. If there's an error, please resend." % (waybill, nets))
                    return json.dumps({"message": ret})
                else:
                    dres = db.query(
                        "INSERT INTO distribution_log (source, dest, waybill, quantity_nets, "
                        "delivered_by, departure_date, departure_time, district_id) VALUES ("
                        "'subcounty', 'dp', $waybill, $nets, $reporter_id, current_date, "
                        "current_time, $district_id) RETURNING id", {
                            'waybill': waybill,
                            'reporter_id': reporter_id,
                            'nets': nets, 'district_id': district_id})
                    if dres:
                        # log_id = dres[0]['id']
                        ret = (
                            "Distribution of %s nets with Delivery Note No. %s successfully recorded. "
                            " VHTs will have to confirm receipt of these nets."
                            " If there's an error, please resend" % (nets, waybill))
                        return json.dumps({"message": ret})
            else:
                ret = "Your phone(%s) is not registered in the system." % phone
            return json.dumps({"message": ret})
