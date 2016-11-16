import web
from . import csrf_protected, db, require_login, get_session, render


class Reporters:
    @require_login
    def GET(self):
        params = web.input(page=1, ed="", d_id="")
        edit_val = params.ed
        session = get_session()
        districts = db.query(
            "SELECT id, name FROM locations WHERE type_id = "
            "(SELECT id FROM locationtype WHERE name = 'district') ORDER by name")
        roles = db.query("SELECT id, name from reporter_groups order by name")
        if params.ed:
            res = db.query(
                "SELECT id, firstname, lastname, telephone, email, national_id, "
                "reporting_location, distribution_point, role, dpoint,alternate_tel "
                "FROM reporters_view "
                " WHERE id = $id", {'id': edit_val})
            if res:
                r = res[0]
                firstname = r.firstname
                lastname = r.lastname
                telephone = r.telephone
                email = r.email
                role = r.role
                national_id = r.national_id
                alt_telephone = r.alternate_tel
                dpoint_id = r.distribution_point
                dpoint = r.dpoint
        if params.d_id:
            if session.role in ('Micro Planning', 'Administrator'):
                db.query("DELETE FROM reporter_groups_reporters WHERE reporter_id=$id", {'id': params.d_id})
                db.query("DELETE FROM reporters WHERE id=$id", {'id': params.d_id})
        if session.role == 'Administrator':
            REPORTER_SQL = "SELECT * FROM reporters_view2"
        else:
            REPORTER_SQL = "SELECT * FROM reporters_view2 WHERE created_by = $user"

        reporters = db.query(REPORTER_SQL, {'user': session.sesid})
        l = locals()
        del l['self']
        return render.reporters(**l)

    @csrf_protected
    @require_login
    def POST(self):
        session = get_session()
        params = web.input(
            firstname="", lastname="", telephone="", email="", location_id="", dpoint="",
            national_id="", role="", alt_telephone="", page="1", ed="", d_id="")
        try:
            page = int(params.page)
        except:
            page = 1

        with db.transaction():
            if params.ed:
                location = params.location if params.location else None
                dpoint = params.dpoint if params.dpoint else None
                r = db.query(
                    "UPDATE reporters SET firstname=$firstname, lastname=$lastname, "
                    "telephone=$telephone, email=$email, reporting_location=$location, "
                    "distribution_point=$dpoint, national_id=$nid, alternate_tel=$alt_tel "
                    "WHERE id=$id", {
                        'firstname': params.firstname, 'lastname': params.lastname,
                        'telephone': params.telephone, 'email': params.email,
                        'location': location, 'dpoint': dpoint, 'nid': params.national_id,
                        'id': params.ed, 'alt_tel': params.alt_telephone
                    })
                db.query(
                    "UPDATE reporter_groups_reporters SET group_id = $gid "
                    " WHERE reporter_id = $id ", {'gid': params.role, 'id': params.ed})
                return web.seeother("/reporters")
            else:
                location = params.location if params.location else None
                dpoint = params.dpoint if params.dpoint else None
                r = db.query(
                    "INSERT INTO reporters (firstname, lastname, telephone, email, "
                    " reporting_location, distribution_point, national_id, alternate_tel, uuid, created_by) VALUES "
                    " ($firstname, $lastname, $telephone, $email, $location, $dpoint,"
                    " $nid, $alt_tel, uuid_generate_v4(), $user) RETURNING id", {
                        'firstname': params.firstname, 'lastname': params.lastname,
                        'telephone': params.telephone, 'email': params.email,
                        'location': location, 'dpoint': dpoint, 'nid': params.national_id,
                        'alt_tel': params.alt_telephone, 'user': session.sesid
                    })
                if r:
                    reporter_id = r[0]['id']
                    db.query(
                        "INSERT INTO reporter_groups_reporters (group_id, reporter_id) "
                        " VALUES ($role, $reporter_id)",
                        {'role': params.role, 'reporter_id': reporter_id})
                return web.seeother("/reporters")

        l = locals()
        del l['self']
        return render.reporters(**l)
