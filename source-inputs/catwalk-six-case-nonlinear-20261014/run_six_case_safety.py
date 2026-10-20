"""在已核验的原网格上补齐六工况几何非线性计算，并按报告口径求索组安全系数。"""  # 只改变各工况荷载与温差，不新增约束。
from pathlib import Path  # 读取冻结模型、源工况和独立输出目录。
import csv  # 保存索组轴力和安全系数，单位在列名中说明。
import hashlib  # 绑定每次运行的输入文件身份。
import json  # 保存工况映射、平衡验证和运行清单。
import os  # 获取本机临时目录以避开资料同步占用。
import re  # 检查节点、单元和温度卡片。
import sys  # 引入同目录的既有源解析器。
import time  # 为本轮生成唯一目录，不覆盖历史结果。
import numpy as np  # 汇总单元轴力、支承反力与自由节点残差。
sys.path.insert(0, str(Path(__file__).parent))  # 优先使用本任务已经核对的执行器。
from run_ansys_same_model import parse, SOURCE, run  # 原工况解析和 ANSYS 2026R1 执行入口。
sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # 终端完整显示中文工况名称。
ROOT = Path(os.environ['TEMP']) / ('catwalk_six_safety_' + time.strftime('%Y%m%d_%H%M%S'))  # 本轮独立的求解目录。
ROOT.mkdir(exist_ok=False)  # 不允许覆写任何已有求解文件。
BASE = Path(r'D:\ppt制作\C05诊断\粗网格四组最终对照\桁架非线性')  # 既有无横向锁定、10 N 局部力门槛的模型。
TEMPLATE = (BASE / 'model.inp').read_text(encoding='utf-8')  # 沿用全部节点、截面、材料、初应力和原支承。
PREFIX = TEMPLATE[:TEMPLATE.index('FDELE,')]  # 保留初始模型及求解控制，首次节点荷载起重新按工况写入。
POSTFIX = TEMPLATE[TEMPLATE.index('FINISH ! 结束两个非线性分析步'):]  # 沿用已核对的位移、反力和轴力输出。
NODES = {int(value) for value in re.findall(r'^N,(\d+),', TEMPLATE, re.M)}  # 原网格物理节点集合，用于校验荷载去向。
assert len(NODES) == 1125  # 原物理节点数量必须与已验证模型一致。
assert len(re.findall(r'^EN,', TEMPLATE, re.M)) == 1194  # 原物理单元必须完整且未增加辅助对象。
assert len(re.findall(r'^D,', TEMPLATE, re.M)) == 54  # 保留原有的五十四个平动支承分量。
AUDIT = ['ALLSEL,ALL ! 选择全部物理对象', 'RSYS,0 ! 端力采用全局直角坐标', '*CFOPEN,element_end_forces,csv ! 输出每个物理单元的端力', "*VWRITE,'eid,node,Fx,Fy,Fz' ! 列名，下一行采用字符串格式", '(A)', 'ee=0 ! 从第一个物理单元开始', '*DO,ii,1,1194 ! 遍历所有原单元', 'ee=ELNEXT(ee) ! 查询下一个单元编号', '*DO,jj,1,2 ! 每个轴杆输出两端节点', '*GET,nn,ELEM,ee,NODE,jj ! 当前端点编号', '*GET,fx,ELEM,ee,EFOR,nn,FX ! 全局纵向端力，牛顿', '*GET,fy,ELEM,ee,EFOR,nn,FY ! 全局横向端力，牛顿', '*GET,fz,ELEM,ee,EFOR,nn,FZ ! 全局竖向端力，牛顿', '*VWRITE,ee,nn,fx,fy,fz ! 输出节点及端力，下一行为数值格式', '(F10.0,",",F10.0,3(",",E24.15))', '*ENDDO ! 结束当前单元两端循环', '*ENDDO ! 结束全体单元循环', '*CFCLOS ! 关闭端力输出']  # 端力含体重等效项，与显式节点力检查闭合。
POSTFIX = POSTFIX.replace('FINISH ! 结束后处理', '\n'.join(AUDIT) + '\nFINISH ! 结束后处理')  # 在最终结果输出后添加独立局部平衡检查数据。
index_path = Path(r'D:\ppt制作\C05诊断\six_case_safety_current.json')  # 当前运行索引，便于用户查看进度。
index_path.write_text(json.dumps({'root': str(ROOT)}, ensure_ascii=False, indent=2), encoding='utf-8')  # 只更新本轮指针，不改旧求解结果。
print('RUN_ROOT=' + str(ROOT), flush=True)  # 首先报告本轮真实运行目录。
models = {}  # 保存各工况解析数据供平衡核查使用。
for case in ('C01', 'C02', 'C03', 'C04', 'C06'):  # C05 已有满载和局部平衡结果，本轮不重复求解。
    model = parse(SOURCE / f'catwalk_base_{case}.inp')  # 读取同源的全工况荷载，原初始状态不变。
    models[case] = model  # 后处理时仍使用同一套节点力。
    temperatures = re.findall(r'^\*TEMPERATURE[^\n]*\n([^\n]+)', (SOURCE / f'catwalk_base_{case}.inp').read_text(encoding='utf-8'), re.M)  # 显式读取旧解析器尚未覆盖的温度卡片。
    assert temperatures == ([] if case not in ('C03', 'C06') else ['NALL, ' + ('-15.000' if case == 'C03' else '-34.000')])  # 温差必须严格等于原工况值，单位摄氏度。
    commands = [PREFIX, 'TREF,0 ! 以原始零摄氏度为无热应变参考温度']  # 保留材料热膨胀系数并明确定义参考温度。
    for step_number, step in enumerate(model['steps'], 1):  # 每个工况独立从自重平衡开始，不串接其他工况。
        commands.append('FDELE,ALL,ALL ! 清除上一分析步节点力，本步按总荷载重写')  # 防止恒载重复累加。
        for (node, dof), value in step['loads'].items():  # 全部保留原始三向节点力。
            assert node in NODES or abs(value) < 1e-12  # 不允许将荷载静默丢在被合并的加密节点上。
            if node in NODES:  # 原节点上输出实际节点力，包括极小力。
                commands.append(f'F,{node},{("FX", "FY", "FZ")[dof - 1]},{value:.16g} ! 原工况完整节点力，牛顿')  # 力方向和单位保持源文件一致。
        temperature = float(temperatures[0].split(',')[1]) if step_number == 2 and temperatures else 0.0  # 第一步零温差，第二步才施加原工况温降。
        commands.append(f'BF,ALL,TEMP,{temperature:.16g} ! 全节点均匀温度，摄氏度；对应原 NALL 温度卡')  # 与原模型均匀温降定义一致。
        commands.append(f'TIME,{step_number} ! 累计伪时间，末步值用于检查达到全荷载')  # 单个分析步持续一个伪时间单位。
        commands.append('DELTIM,0.025,0.000001,0.05 ! 初始和最大增量沿用已验证风载设置，最小增量为百万分之一')  # 仅采用更细数值增量，不改变载荷或物理模型。
        commands.append('KBC,0 ! 从前一平衡态平滑加载到当前总力及温度')  # 继承非线性变形和内力状态。
        commands.append('SOLVE ! 求当前几何非线性平衡，不进行线性结果叠加')  # 沿用全 Newton 更新和原残差门槛。
    folder = ROOT / case  # 每个工况单独存放完整输入和结果。
    folder.mkdir()  # 唯一目录内新建子目录。
    deck = '\n'.join(commands) + '\n' + POSTFIX  # 合成完整可复现输入。
    (folder / 'model.inp').write_text(deck, encoding='utf-8')  # 保存实际求解输入及逐行中文说明。
    mapping = {'case': case, 'source': str(SOURCE / f'catwalk_base_{case}.inp'), 'template': str(BASE / 'model.inp'), 'sha256': hashlib.sha256(deck.encode('utf-8')).hexdigest(), 'physical_nodes': len(NODES), 'physical_elements': 1194, 'fixed_translation_dofs': 54, 'geometric_nonlinearity': True, 'wind_force_update': False, 'final_temperature_C': temperature, 'force_tolerance_N': 10, 'displacement_correction_m': 0.00001}  # 记录固定外力的几何非线性计算范围和输入身份。
    (folder / 'mapping.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')  # 元数据避免误称气动力随攻角更新。
    print('START=' + case, flush=True)  # 报告当前工况开始运行。
    run(folder)  # 使用既有 ANSYS 执行器，保存日志和退出状态。
print('SOLVES_COMPLETE=' + str(ROOT), flush=True)  # 这里只表示求解调用结束，工程通过须等待局部平衡与安全系数核对。
