import json
import threading
import time
import uuid
import sys
from typing import Optional
from qrcode import QRCode
import uvicorn
import mimetypes
from threading import Thread
import threading


from starlette.responses import StreamingResponse, Response, HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocketState
from web.chaoxingWorker import Multitasking

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware

from web.utils import chaoxing_web_prompt
from cxapi.api import ChaoXingAPI
from cxapi import (ChapterContainer)


from main import (
    on_captcha_after,
    on_captcha_before,
    on_face_detection_after,
    on_face_detection_before,
    fuck_task_worker
)

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/png", ".png")

app = FastAPI()
api = ChaoXingAPI()
user_sessions = {}

# 用于保存任务线程的状态
task_threads = {}

from utils import (
    SessionModule,
    __version__,
    ck2dict,
    mask_name,
    mask_phone,
    save_session,
    is_exist_session,
    session_load
)


# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
)
def get_api(phone: str):
    print(phone)
    if phone in user_sessions:
        return user_sessions[phone]
    api = ChaoXingAPI()
    user_sessions[phone] = api
    return api


# 处理预检请求
@app.options("/{rest_of_path:path}", include_in_schema=False)
async def preflight_handler(rest_of_path: str):
    return Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Credentials": "true",
    })


multitasking = Multitasking()


# 创建新的工作线程
def create_process():
    process_id = uuid.uuid4().hex
    multitasking.create_process(process_id)
    return process_id




# 获取工作线程的ID
@app.get("/get_process_id")
def get_process_id(phone: str):
    process_id = multitasking.get_process_id(phone)
    if process_id is None:
        print("没找到这个手机号的进程ID", phone)
        process_id = create_process()

    for i in multitasking.tasks:
        print(i.process_id, i.phone)
    print('分配工作线程id', process_id)

    return {"status": "success", "process_id": process_id}

@app.get("/check_phone")
def check_phone(phone: str, api: ChaoXingAPI = Depends(get_api)):
    if not is_exist_session(phone):
        return {"code":2,"status": "error", "msg": "手机号未登录"}
    else:
        session=session_load(phone)
        api.session.ck_clear()
        phone = session.phone
        passwd = session.passwd
        if passwd is not None:
            status, result = api.login_passwd(phone, passwd)
            if status:
                api.accinfo()
                save_session(api.session.ck_dump(), api.acc, passwd)
                return {"code":200,"status": "success", "msg": "手机号已登录","account":{"puid":api.acc.puid,"name":api.acc.name,"sex":api.acc.sex.name,"phone":api.acc.phone,"school":api.acc.school,"stu_id":api.acc.stu_id}}
            else:
                return {"code":1,"status": "error", "msg": "手机号登录失败"}
        else:
            return {"code":2,"status": "error", "msg": "已无法登录"}


@app.get("/login")
def login(phone: str, passwd: str, api: ChaoXingAPI = Depends(get_api)):
    status= api.login_passwd(phone, passwd)

    if status:

        # process.phone = uname  # 更新进程的手机号

        # tui_ctx.print("[green]登录成功")
        # tui_ctx.print(result)
        api.accinfo()
        save_session(api.session.ck_dump(), api.acc, passwd)
        return {"code": 200, "status": "success", "msg": "登录成功", "account": api.acc}
    else:
        return {"code": 1, "status": "error", "msg": "登录失败"}


@app.get("/qr_code")
def qr_code(phone:str, api: ChaoXingAPI = Depends(get_api)):
    """
    获取二维码数据
    """
    api.qr_get()
    return {"code": 200, "status": "success", "qr_data": api.qr_geturl()}

@app.get("/qr_status")
def check_status(phone:str, api: ChaoXingAPI = Depends(get_api)):
    """
    检查二维码状态
    """

    qr_status = api.login_qr()
    print(qr_status)

    if qr_status.get("status") is True:
        api.accinfo()
        # 模拟保存会话
        save_session(api.session.ck_dump(), api.acc)
        account_info = api.acc
        return {
            "code": 200,
            "status": "success",
            "msg": "登录成功",
            "account": account_info
        }

    match qr_status.get("type"):
        case "1":
            return {"code": 1, "status": "error", "msg": "二维码验证错误"}
        case "2":
            return {"code": 2, "status": "error", "msg": "二维码已失效"}
        case "4":
            return {"code": 4, "status": "error", "msg": "二维码已扫描", "account": {"name": qr_status["nickname"], "puid": qr_status["uid"]}}
        case "3":
            return {"code": 3, "status": "error", "msg": "未登录"}


@app.get('/get_class')
def get_class(phone: str, api: ChaoXingAPI = Depends(get_api)):
    classContainer = api.fetch_classes()
    return {
        "code":200,
        "status": "success",
        "classes": classContainer.classes
    }



@app.get("/task_work")
def task_work(phone: str,course_ids:str, api: ChaoXingAPI = Depends(get_api)):

    ids = course_ids.split(",")
    session = api.session
    print(ids)
    # 检查是否已有任务在运行
    if phone in task_threads and task_threads[phone].is_alive():
        print("已有任务在运行")
        classContainer = api.fetch_classes()
        coures=[]
        for i, v in enumerate(classContainer.classes):
            if str(v.course_id) in ids:
    
                # chapters=classContainer.get_chapters_by_index(i)
                chap=ChapterContainer(
                        session=session,
                        acc=api.acc,
                        courseid=v.course_id,
                        name=v.name,
                        classid=v.class_id,
                        cpi=v.cpi,
                        chapters=classContainer.get_chapters_by_index(i)
                    )
                progress=chap.fetch_point_status()
                coures.append({
                                "name": v.name,
                                "class_id": v.class_id,
                                "progress": progress
                })
        return {"code": 1, "status": "error", "msg": "任务正在运行，请稍后再试","progress":coures}


    
    # 定义任务函数
    def run_task():
        
        # 注册回调函数
        api.session.reg_captcha_after(on_captcha_after)
        api.session.reg_captcha_before(on_captcha_before)
        api.session.reg_face_after(on_face_detection_after)
        api.session.reg_face_before(on_face_detection_before)
        
        # 开始任务
        for chap in chaps:
            fuck_task_worker(chap)
        # 任务完成后移除线程记录
        del task_threads[phone]


    classContainer = api.fetch_classes()
    chaps=[]
    coures=[]
    for i, v in enumerate(classContainer.classes):
        # 主要是这个函数，是用来刷课的
        print(v.course_id)
        if str(v.course_id) in ids:
            print(f"开始刷课 ==> name: {v.name} id: {v.class_id}")
            chap=ChapterContainer(
                session=session,
                acc=api.acc,
                courseid=v.course_id,
                name=v.name,
                classid=v.class_id,
                cpi=v.cpi,
                chapters=classContainer.get_chapters_by_index(i)
            )
            chaps.append(chap)
            coures.append({
                "name": v.name,
                "class_id": v.class_id,
                "progress": chap.fetch_point_status()
            })

    # 创建并启动线程
    task_thread = Thread(target=run_task)
    task_thread.start()

    # 启动任务过后，写入日志文件中
    with open("log.txt", "a",encoding='utf8') as f:
        f.write(f"任务开始: {phone}\n")
        f.write(f"任务课程id:  {course_ids}\n")
    # 保存线程状态
    task_threads[phone] = task_thread

    return {"code": 200, "status": "success", "msg": "任务已启动","progress":coures}

        
@app.get("/")
@app.get("/index")
async def read_root():
    return RedirectResponse(url="/static/index.html")


# 静态文件
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 提供 SPA 回退支持
@app.get("/static/{path:path}")
async def serve_spa(path: str):
    # 如果请求的文件不存在，返回 index.html
    try:
        return FileResponse(f"web/static/{path}")
    except FileNotFoundError:
        return FileResponse("web/static/index.html")

# 启动uvicorn服务，默认端口8000，main对应文件名
if __name__ == '__main__':
    uvicorn.run('app:app', host="0.0.0.0", port=2333,reload=True)
