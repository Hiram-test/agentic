"""核查六工况满载和局部平衡，按原报告破断力及安全系数门槛筛选最不利结果。"""  # 输出为索组强度对照，不代表新增气动稳定性验证。
from pathlib import Path  # 管理运行索引、原始结果和可长期保留的对照表。
import csv  # 写入全部四十八个工况与索组结果。
import json  # 保存结果来源、输入核对和残差。
import shutil  # 原样复制关键输入和文本结果。
import sys  # 定位既有模型解析器并设置中文输出。
import numpy as np  # 读取轴力、位移和端力结果并完成平衡检查。
sys.path.insert(0, str(Path(__file__).parent))  # 复用已核对的源输入解析器。
from run_ansys_same_model import parse, SOURCE  # 从原工况读取显式节点载荷和原支承。
sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # 确保终端可以显示中文索组名称。
WORK = Path(__file__).parent  # 本轮核查脚本目录，也是固定证据入口。
ROOT = Path(json.loads((WORK / 'six_case_safety_current.json').read_text(encoding='utf-8'))['root'])  # 只读取本轮实际求解目录。
OUT = WORK / '六工况非线性安全系数'  # 为用户保留表格及关键证据，不依赖临时目录。
OUT.mkdir(exist_ok=True)  # 仅创建结果目录，不清除既有文件。
raw = json.loads(Path(r'D:\bridgemind\BridgeMind_Simulation_Studio_1.5.2\runs\dsh-native\workspaces\17a00fbe85854e73896342299cbf53b4\99_audit\mct_extract.json').read_text(encoding='utf-8'))  # 原 MCT 单元映射。
reverse = {}  # 将此前细分索段映射回本轮原网格。
next_element = 1  # 细分编号从一开始，与既有生成器相同。
for original_id, element in sorted((int(key), value) for key, value in raw['elements'].items()):  # 原 MCT 顺序固定。
    count = 2 if element['type'] == 'TENSTR' else 1  # 原索曾二分，原桁架未细分。
    for refined_id in range(next_element, next_element + count):  # 两半段归属于同一原单元。
        reverse[refined_id] = original_id  # 建立分组回投关系。
    next_element += count  # 移到下一原构件的细分编号。
fine_groups = json.loads((WORK / 'ansys_same_model' / 'group_refined_element_ids.json').read_text(encoding='utf-8'))  # 八个已核对的索组集合。
groups = {name: sorted({reverse[element] for element in ids}) for name, ids in fine_groups.items()}  # 恢复到原网格编号。
reference_values = [  # 原复核报告第 30 和 39 页的索组轴力，单位 kN；每行依次为猫道四跨、门架四跨。
    [11466, 11005, 10928, 10338, 3554, 3348, 3381, 3233],  # 工况一：恒载。
    [12317, 12624, 11803, 11140, 3856, 3962, 3688, 3514],  # 工况二：恒载加施工荷载。
    [12572, 12657, 12047, 11378, 3963, 3974, 3788, 3613],  # 工况三：施工组合加降温十五摄氏度。
    [12380, 12741, 11869, 11200, 3879, 4007, 3710, 3535],  # 工况四：施工组合加六级风。
    [11892, 11802, 11368, 10741, 3705, 3650, 3534, 3374],  # 工况五：恒载加最大阵风。
    [12906, 12700, 12365, 11689, 4102, 3989, 3919, 3743],  # 工况六：施工组合加降温三十四摄氏度。
]  # 所有数值来自原报告，不用于调整模型或索力。
required_factors = [3.2, 2.7, 2.7, 2.7, 2.5, 2.7]  # 采用原报告第 11 页表 1-7；工况六正文误写的 2.5 不作为门槛。
ordered_names = ['北边跨', '主跨', '南边跨', '南辅跨', '门架索北边跨', '门架索主跨', '门架索南边跨', '门架索南辅跨']  # 与原报告两张表的列顺序一一对应。
checks, rows, case_summaries = {}, [], []  # 分别保存验证证据、完整结果与每工况控制结果。
base_model = parse(SOURCE / 'catwalk_base_C05.inp')  # 初始状态一致性检查的已验证参照。
for case_number in range(1, 7):  # 完整检查六个工况，不预先假定最大阵风必然控制。
    case = f'C{case_number:02d}'  # 与原计算输入统一的工况标识。
    folder = WORK / '粗网格四组最终对照' / '桁架非线性' if case_number == 5 else ROOT / case  # 工况五复用已核验结果，其余使用本轮运行。
    source_model = parse(SOURCE / f'catwalk_base_{case}.inp')  # 当前工况真实的源荷载。
    for field in ('nodes', 'elements', 'materials', 'sections', 'stresses', 'boundary'):  # 核查几何、物性、初应力与支承不随工况偷换。
        assert source_model[field] == base_model[field], f'{case}: 初始模型字段不一致: {field}'  # 发现差异即停止给出统一模型结论。
    history = np.atleast_2d(np.loadtxt(folder / 'history.csv', delimiter=',', skiprows=1))  # 真实收敛结果中的累计时间。
    assert abs(history[-1, 1] - len(source_model['steps'])) < 1e-9  # 必须达到最终完整加载状态。
    run_record = json.loads((folder / 'run.json').read_text(encoding='utf-8'))  # 读取真实求解日志状态。
    assert run_record['returncode'] == 0 and not run_record['errors']  # 不使用退出异常或错误结果。
    nodes = np.atleast_2d(np.loadtxt(folder / 'final_nodes.csv', delimiter=',', skiprows=1))  # 原节点位移与支承反力，单位 m、N。
    node_index = {int(row[0]): index for index, row in enumerate(nodes)}  # 端力与节点力汇总索引。
    residual = nodes[:, 4:7].copy()  # 将支反力纳入节点平衡。
    for (node, dof), force in source_model['steps'][-1]['loads'].items():  # 当前满载组合的显式节点力。
        if node in node_index:  # 只含原物理节点，细分中点本来无独立外力。
            residual[node_index[node], dof - 1] += force  # 单位 N，与结果端力同一坐标系。
        else:  # 不应丢失任何实际载荷。
            assert abs(force) < 1e-12  # 只有严格近零的细分中点力可忽略。
    for end_force in np.loadtxt(folder / 'element_end_forces.csv', delimiter=',', skiprows=1):  # 全局单元端力中含体重等效修正。
        residual[node_index[int(end_force[1])]] += end_force[2:5]  # 汇入其所属物理节点。
    free = np.ones_like(residual, dtype=bool)  # 默认所有平动分量参与自由节点残差检查。
    for node, dof, value in source_model['boundary']:  # 只排除原 MCT 的支承分量。
        free[node_index[node], dof - 1] = False  # 不引入额外固定点。
    max_residual = float(np.max(np.abs(residual[free])))  # 全模型最大自由平动残差，单位 N。
    assert max_residual < 10  # 沿用原受检求解的十牛顿局部门槛。
    checks[case] = {'source': str(folder), 'final_time': float(history[-1, 1]), 'max_free_residual_N': max_residual, 'max_uy_m': float(history[-1, 2]), 'warnings': run_record['warnings'], 'global_residual_force_N': np.sum(residual, axis=0).tolist()}  # 保存验证证据，不将数值通过误称工程签认。
    forces = {int(row[0]): float(row[1]) for row in np.loadtxt(folder / 'final_elements.csv', delimiter=',', skiprows=1)}  # 按原单元号读取轴力，拉为正。
    current_rows = []  # 本工况八个索组结果。
    for group_index, name in enumerate(ordered_names):  # 逐组取峰值而非跨组平均。
        critical_element = max(groups[name], key=lambda element: forces[element])  # 定位组内最大拉力所在原单元。
        force_kN = forces[critical_element] / 1000  # 牛顿转换为千牛，匹配报告破断力。
        capacity_kN = 14280.0 if name.startswith('门架') else 38080.0  # 原报告的门架和猫道索组总破断力，单位 kN。
        factor = capacity_kN / force_kN  # 沿用原报告的破断力除以最大轴力口径。
        required = required_factors[case_number - 1]  # 当前工况规定门槛。
        reference = reference_values[case_number - 1][group_index]  # 原报告同工况同索组轴力，单位 kN。
        row = {'case': case, 'group': name, 'critical_element': critical_element, 'force_kN': force_kN, 'breaking_force_kN': capacity_kN, 'safety_factor': factor, 'required_factor': required, 'factor_to_required': factor / required, 'reference_force_kN': reference, 'reference_factor': capacity_kN / reference, 'force_change_percent': (force_kN / reference - 1) * 100}  # 所有导出字段均标明量纲或比例意义。
        rows.append(row)  # 记录完整四十八组明细。
        current_rows.append(row)  # 为当前工况筛选控制位置。
    catwalk = min(current_rows[:4], key=lambda row: row['safety_factor'])  # 猫道承重索四跨中的最小安全系数。
    gantry = min(current_rows[4:], key=lambda row: row['safety_factor'])  # 门架承重索四跨中的最小安全系数。
    case_summaries.append({'case': case, 'catwalk': catwalk, 'gantry': gantry, 'verification': checks[case]})  # 保存两种构件的控制结果。
    target = OUT / case  # 每个工况的关键证据独立存放。
    target.mkdir(exist_ok=True)  # 不移动原始求解文件。
    for filename in ('model.inp', 'model.out', 'model.err', 'mapping.json', 'run.json', 'final_nodes.csv', 'final_elements.csv', 'history.csv', 'element_end_forces.csv'):  # 保存足以重查算法和结果的文本，不复制庞大二进制。
        if (folder / filename).exists():  # 少数历史运行不提供可选文件。
            shutil.copy2(folder / filename, target / filename)  # 原样复制，保留修改时间。
with (OUT / '六工况索组安全系数.csv').open('w', encoding='utf-8-sig', newline='') as stream:  # 用 Excel 可读编码保存完整明细。
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))  # 固定字段顺序。
    writer.writeheader()  # 写入列名与量纲。
    writer.writerows(rows)  # 写入六工况八索组的未舍入结果。
summary = {'source_root': str(ROOT), 'checks': checks, 'cases': case_summaries, 'minimum_factor': min(rows, key=lambda row: row['safety_factor']), 'minimum_factor_to_required': min(rows, key=lambda row: row['factor_to_required']), 'scope': '同原MCT固定外力的几何非线性分析；未新增随攻角更新气动力；使用原报告索组破断力与表1-7门槛'}  # 区分绝对安全系数最低与距各自门槛最近。
(OUT / '核查摘要.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')  # 保留所有可审核数值及结果边界。
lines = ['# 六工况几何非线性安全系数', '', '| 工况 | 猫道控制跨 | 猫道最小系数 | 门架控制跨 | 门架最小系数 | 要求 |', '|---|---|---:|---|---:|---:|']  # 用户可直接查看的简明表格。
for item in case_summaries:  # 完整列出每个工况最不利位置。
    catwalk, gantry = item['catwalk'], item['gantry']  # 两类索组的控制行。
    lines.append(f"| {item['case']} | {catwalk['group']} | {catwalk['safety_factor']:.4f} | {gantry['group']} | {gantry['safety_factor']:.4f} | {catwalk['required_factor']:.1f} |")  # 四位小数便于核查不同门槛。
lines += ['', '计算范围：'+summary['scope'], '', '所有工况已达到完整荷载，最大自由节点平动残差均小于10 N。', 'C06门槛按报告第11页表1-7取2.7；报告第29页正文的2.5与该表不一致。']  # 注明计算边界和原报告文字差异。
(OUT / '六工况最不利对照.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')  # 保存可读结果。
print('\n'.join(lines), flush=True)  # 终端输出每工况的控制结果。
print(json.dumps({'minimum_factor': summary['minimum_factor'], 'minimum_factor_to_required': summary['minimum_factor_to_required'], 'checks': checks}, ensure_ascii=False, indent=2), flush=True)  # 输出最不利工况和局部平衡证据。
