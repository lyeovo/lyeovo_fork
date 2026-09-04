%% =========================================================================
% 空间蛇形臂主控 UI 与 MATLAB 算法端闭环联调启动脚本
%
% 控制仓库路径：F:\Grade3\study\Hyper-Redundant-Snake-Robot-Manipulator-Algorithm-main
% 主控 UI 路径：F:\Grade3\study\D405+UI\SpaceSnakeVisionUI
% =========================================================================

clc;
clear;
fprintf('=================================================================\n');
fprintf('🚀 正在启动空间蛇形机械臂控制算法任务循环 (MATLAB Bridge)...\n');
fprintf('=================================================================\n');

% 1. 切换到控制仓库目录
control_repo = 'F:\Grade3\study\Hyper-Redundant-Snake-Robot-Manipulator-Algorithm-main';
if exist(control_repo, 'dir')
    cd(control_repo);
    fprintf('📁 已进入控制仓库目录: %s\n', control_repo);
else
    warning('未找到目录 %s，使用当前目录: %s', control_repo, pwd);
end

% 2. 自动添加 ArmSimulator2D 依赖
if exist(fullfile(pwd, 'ArmSimulator2D'), 'dir')
    addpath(fullfile(pwd, 'ArmSimulator2D'));
    fprintf('✓ 已加载 ArmSimulator2D 运动学核心模型库\n');
end

% 3. 构造 6-DoF 蛇形机械臂标准运动模型（显式指定 N=6）
try
    model = createArmModel(struct('N', 6));
    fprintf('✓ 机械臂模型构建成功 (N=%d 关节, 杆长=%.3f m, 展开全长=%.2f m)\n', ...
        model.cfg.N, model.cfg.L_seg(1), sum(model.cfg.L_seg));
catch ME
    error('构建机械臂模型失败: %s', ME.message);
end

% 4. 配置 UI 通信桥接目录
opts = struct();
opts.outbox = 'F:/Grade3/study/D405+UI/SpaceSnakeVisionUI/data/outbox';
opts.inbox  = 'F:/Grade3/study/D405+UI/SpaceSnakeVisionUI/data/inbox';
opts.poll_interval = 0.2;  % 200 ms 轮询更新
opts.method = 'auto';      % 自动选用最佳规划器 (Momentum / CVAE / RRT*)
opts.verbose = true;       % 开启详细控制台输出

% 确保通信目录存在
if ~exist(opts.outbox, 'dir'), mkdir(opts.outbox); end
if ~exist(opts.inbox, 'dir'),  mkdir(opts.inbox);  end

fprintf('-----------------------------------------------------------------\n');
fprintf('📥 正在监听 UI 任务发布 (outbox): %s\n', opts.outbox);
fprintf('📤 状态实时写回目录     (inbox) : %s\n', opts.inbox);
fprintf('💡 提示：此时在 Python 总控 UI 上发布任意任务，MATLAB 将自动计算并执行！\n');
fprintf('         按 Ctrl+C 可终止任务监听循环。\n');
fprintf('=================================================================\n\n');

% 5. 启动常驻任务循环执行器
stats = runTaskLoop(model, opts);
