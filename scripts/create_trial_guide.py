"""Build a self-contained offline guide. Screenshots contain synthetic demo data only."""
from pathlib import Path
import base64
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from container_planner import __version__
OUT = ROOT / "docs/release"


def image(name, label, height):
    data = base64.b64encode((ROOT / "docs/assets" / name).read_bytes()).decode()
    return f'<figure><img alt="{label}" style="max-height:{height}px" src="data:image/png;base64,{data}"><figcaption>{label}（图中均为练习数据）</figcaption></figure>'


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pages = []
    pages.append('''<div class="kicker">木序 · Windows 试用版 · 1.1.0-beta.2</div><h1>从客户订单到排柜 Excel</h1><p class="lead">给第一次使用的朋友：先走通一次练习，再处理真实订单。</p>
<h2>1. 解压后，双击启动</h2><ol><li>把收到的 ZIP 保存到电脑，右键选择<strong>“全部解压”</strong>。不要在压缩包预览窗口里直接运行。</li><li>打开解压后的文件夹，双击<strong>“启动排柜工具.bat”</strong>。程序会自动打开浏览器工作台，不用安装 Python、Node 或服务器。</li><li>保留同目录的 <code>runtime</code> 和 <code>app</code> 文件夹。下次仍双击同一个启动程序。</li></ol>
<div class="note">适用：Windows 10 / 11，Intel 或 AMD 的 64 位电脑。此包不面向 Windows ARM / 32 位系统。建议使用 Edge 或 Chrome。首次启动请等待约 10～30 秒。</div>
<h2>2. 第一次先试练习示例</h2><p>首页点击<strong>“先用练习示例体验”</strong>，会载入三家工厂的虚构产品和一份带“【练习】”的订单。已有业务资料时，此按钮不会覆盖它们。</p>
'''+image("manual-review.png", "订单按三步处理：导入订单 → 处理问题 → 排柜并导出", 260)+'''
<h2>3. 练习的成功标志</h2><p>把 700 件床头柜分为 <strong>2027-01-11 发 350 件、2027-01-18 发 350 件</strong>，保存后生成排柜方案并下载 Excel。默认结果为 4 个柜，三家工厂分别安排。</p><p class="muted">练习数据会留在历史中并标明“【练习】”。真实订单请通过“我的排柜 → 新建排柜”另建，不要修改练习订单充当真实订单。</p>''')
    pages.append('''<div class="kicker">使用指南 · 2 / 4</div><h1>“需要确认”到底要做什么？</h1><p>系统只会拦下缺少依据或分配不一致的行。表格会写出处理内容，点击右侧<strong>“处理”</strong>查看原因与要填写的内容。</p>'''+image("manual-reason.png", "先看原因，再按“请你确认”填写", 160)+'''
<table><tr><th>提示</th><th>原因与操作</th></tr><tr><td>多个交期，数量未拆分</td><td>订单列了多个日期，但未说明每次发多少。添加各批次日期与数量，合计等于本行排柜数量。</td></tr><tr><td>订单产品尚未对应到产品资料</td><td>选择正确产品。先按编码、OEM或名称搜索，并核对款式、颜色；找不到时到“资料设置”补建。</td></tr><tr><td>产品所属工厂未确认</td><td>不同工厂不能合柜。点击补资料入口，核实该款由哪家工厂供货，保存后返回订单。</td></tr><tr><td>体积、毛重缺失或冲突</td><td>按一件完整产品的全部包装核实 CBM（m³）和毛重（kg），不要把净重当作毛重。</td></tr><tr><td>批次数量与排柜数量不一致</td><td>对照提示的合计与差额，修正分配。增减了排柜数量，也要同步修改各批次数量。</td></tr></table>
<h2>练习：填写两次发货</h2><ol><li>打开练习床头柜那一行，点击“添加批次”。第一个日期选 2027-01-11，数量填 350。</li><li>再次“添加批次”，日期选 2027-01-18，数量填 350。检查“已分配 700 / 700 件”。</li><li>点击底部“保存审核结果”。待确认行清零后，点击右上角“进入排柜”。</li></ol>
<div class="note">不要求重新审核已经就绪的每一行。问题类型的行数可能重叠，同一行可能同时缺少产品、工厂或交期。</div>
<h2>没有LSD的订单</h2><p>勾选“先排柜，LSD稍后按柜填写”，可以直接排柜。在排柜页选择柜子填写LSD，再“另存新版本”后导出。已有明确日期仍按原日期隔离；原订单列了多个日期时，需先确认每次发货数量。</p><h2>批量操作怎么用</h2><p>勾选订单行后，可把<strong>选中行的全部数量</strong>放到同一日期。这会替换这些行原有的批次分配，不能用来自动平均拆分多个日期。确实本次不发的行，可填原因后选择“本次不参与”，导出会另列这些行。</p>''')
    pages.append('''<div class="kicker">使用指南 · 3 / 4</div><h1>生成方案、调整与导出</h1><ol><li>点击<strong>“生成推荐方案”</strong>，等待计算完成。结果会自动保存。</li><li>从左边按工厂查看柜子，核对目的仓、日期、件数和余量。</li><li>有手动修改时先点<strong>“另存新版本”</strong>，再点<strong>“导出 Excel”</strong>。浏览器通常保存到“下载”文件夹。</li></ol>'''+image("manual-workspace.png", "柜列表、装载余量与导出按钮", 310)+'''
<table><tr><th>柜型</th><th>最大体积</th><th>最大毛重</th></tr><tr><td>20GP</td><td>28 m³</td><td>22,800 kg</td></tr><tr><td>40GP</td><td>58 m³</td><td>22,800 kg</td></tr><tr><td>40HQ</td><td>68 m³</td><td>22,800 kg</td></tr></table>
<p><strong>合柜边界：</strong>先按工厂，再按目的仓、发货日期分别安排。NEW新品与常规品分柜。系统依次尽量减少柜数、同款拆柜次数、ABC等级混装和柜型大小。达到计算预算时仍可返回可行方案；“未证明最优”表示还不能保证已找到最优解。</p>
<p><strong>移货与锁柜：</strong>产品行右侧可移到同工厂、同仓、同批次且同新品类别的其他柜或新柜。锁定后该柜在重算时保持分配；调整后的超容、超重方案不能保存为正式版本。</p>
<p><strong>Excel内容：</strong>排柜明细、每柜合计与Summary。原数量与调整数量分别保留；有改量时另附“数量调整”表，列出差额和原因；人工排除的行附在“未参与订单”中。导出代表排柜计划，不代表已实际发货。</p>''')
    pages.append('''<div class="kicker">使用指南 · 4 / 4</div><h1>真实资料、备份与反馈</h1>
<h2>真实订单怎么开始</h2><ol><li>在<strong>“资料设置 → 导入或更新基础资料”</strong>先导入产品编码、名称、单件CBM和毛重，再导入工厂产品表。工厂表可按各工作表识别归属，不能唯一匹配的要确认。价格表可选。</li><li>回到<strong>“我的排柜 → 新建排柜”</strong>上传客户订单。核对工作表、表头、产品、目的仓数量和LSD的字段对应。支持 .xlsx 和 .csv，旧 .xls 请先另存为 .xlsx。同表并列件数和CBM时选件数列；选到产品资料表时切换订单表，或到资料设置导入。</li><li>处理提示后再生成方案。名称相近不代表同款；日期中的年份也要核对，系统不会擅自改成下一年。</li></ol>
<h2>本次确认的数量规则</h2><p>空白仓数量视为0。正数订单向上凑至5的倍数，每款四仓合计自动增加不超过30件，尽量补至100件。例：49件补至75件，80件补至100件。只补原本有订单的仓，按原下单比例分配；不足100件会提示，不强行超量。审核页可筛选“有数量调整”，导出查看“数量调整”表。</p><h2>保存、退出与换电脑</h2><p>产品和订单修改、已保存方案在本机留存，关闭浏览器不会清空。要停掉程序，用左下角“退出工具”。未保存的柜内调整需先另存版本。</p><p>每次重要处理后，在<strong>“历史与备份”下载完整ZIP备份</strong>。换电脑时，在新电脑启动工具后从同一页面恢复备份。恢复会替换当前资料，并保留恢复前的数据目录。程序包不包含你的真实业务资料；给朋友迁移真实资料时需另外发送你决定分享的备份。</p>
<table><tr><th>遇到的情况</th><th>先这样处理</th></tr><tr><td>双击后没有打开页面</td><td>确认已完整解压，保留 runtime 和 app。等待30秒再试；仍失败请运行“遇到问题请运行自检.bat”，截图报错。</td></tr><tr><td>系统或单位策略阻止运行</td><td>核对压缩包来源和版本；企业电脑请交由管理员确认，不要关闭安全软件。</td></tr><tr><td>导出按钮不可用</td><td>检查是否有未保存调整、排柜还在计算，或订单问题尚未处理完。</td></tr><tr><td>下载后找不到Excel</td><td>查看浏览器的下载记录，或到“历史与备份”再次下载。</td></tr><tr><td>更新后看不到旧资料</td><td>确认在同一Windows用户下使用。默认路径：%LOCALAPPDATA%\\WoodFlow\\ContainerPlanner；实际路径在“历史与备份”显示。</td></tr></table>
<p><strong>下次更新：</strong>先备份并在旧工作台点“退出工具”，再把新版解压到新的文件夹，用同一Windows账户打开。不要同时运行新旧版本；原业务资料保存在用户目录，保留完整备份更稳妥。</p><h2>反馈请带上这四项</h2><p>① 版本号和Windows版本；② 卡在哪一步、点了什么；③ 期望发生什么、实际发生什么；④ 提示截图。可直接填写包内“反馈记录.txt”。分享截图前自行遮住不需要提供的客户信息。</p>
<p class="muted">此工具分配产品和件数，不计算箱子在柜内的具体位置、堆叠或承重。把握好真实资料的计量口径，再按实际装柜条件核对方案。</p>''')
    css = '''*{box-sizing:border-box}body{font-family:"PingFang SC","Microsoft YaHei",Arial,sans-serif;background:#eef2ef;color:#243d33;margin:0;font-size:14px;line-height:1.7}.sheet{width:850px;margin:24px auto;background:white;padding:44px 48px;box-shadow:0 4px 22px #1232}.kicker{font-size:12px;color:#64856b;letter-spacing:1px}h1{font-size:28px;line-height:1.4;margin:12px 0 18px}h2{font-size:17px;margin:20px 0 8px}p{margin:8px 0}ol{padding-left:23px;margin:9px 0}li{margin:7px 0}.lead{color:#6b7c6d;font-size:16px}.note{padding:12px 16px;background:#eef5ed;border-left:3px solid #72936e;margin:14px 0;font-size:13px}.muted{font-size:12px;color:#7a8979}table{width:100%;border-collapse:collapse;font-size:13px;margin:16px 0}th{background:#2d5545;color:white;text-align:left}td,th{padding:9px 12px;border-bottom:1px solid #dfe7dd;vertical-align:top}td:first-child{width:28%;font-weight:600}figure{margin:14px 0}img{display:block;width:100%;object-fit:contain;border:1px solid #dfe6dc}figcaption{font-size:11px;color:#82917c;text-align:center;margin-top:6px}code{background:#f0f3ed;padding:2px 4px}@page{size:A4;margin:13mm 14mm}@media print{body{background:white;font-size:10pt;line-height:1.5}.sheet{width:auto;margin:0;padding:0;box-shadow:none;break-after:page}.sheet:last-child{break-after:auto}h1{font-size:22pt;margin:8px 0 12px}h2{font-size:12pt;margin:16px 0 6px}.kicker{font-size:9pt}.lead{font-size:11pt}table{font-size:9pt;margin:12px 0}td,th{padding:7px 9px}.note{font-size:9pt;padding:9px 12px;margin:10px 0}.muted{font-size:8.5pt}li{margin:5px 0}figure{margin:10px 0}figcaption{font-size:8pt}.sheet img{max-height:220px!important}p{margin:6px 0}}'''
    html = '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><title>木序排柜试用指南</title><style>'+css+'</style>' + ''.join('<section class="sheet">'+p+'</section>' for p in pages)+'</html>'
    html = html.replace('1.1.0-beta.2', __version__)
    (OUT / "使用指南.html").write_text(html, encoding="utf-8")
    (OUT / "开始使用.txt").write_text("木序排柜 Windows试用版 1.1.0-beta.2\n\n1. 右键ZIP，选择全部解压。\n2. 打开解压后的文件夹，双击 启动排柜工具.bat。\n3. 第一次建议点击 先用练习示例体验。\n4. 详细步骤请打开 使用指南.pdf 或 使用指南.html。\n\n请保留 runtime 和 app 文件夹。程序和资料保存在本机，无需安装Python或Node。\n启动失败可运行 遇到问题请运行自检.bat，并截图反馈。\n支持Windows 10/11 Intel/AMD 64位。\n", encoding="utf-8-sig")
    (OUT / "反馈记录.txt").write_text("木序排柜试用反馈\n\n程序版本：1.1.0-beta.2\nWindows版本（如Windows11）：\n电脑是Intel/AMD还是ARM：\n使用练习数据还是真实订单：\n\n在哪一步遇到问题（启动/导入/处理问题/排柜/导出/备份）：\n我依次点击了：\n我希望得到：\n实际发生了：\n屏幕提示原文：\n能否重复出现：\n\n请另附截图；分享前遮住不需要提供的客户信息。\n", encoding="utf-8-sig")
    for name in ("开始使用.txt", "反馈记录.txt"):
        p = OUT / name
        p.write_text(p.read_text(encoding="utf-8-sig").replace("1.1.0-beta.2", __version__), encoding="utf-8-sig")
    print(OUT / "使用指南.html")
