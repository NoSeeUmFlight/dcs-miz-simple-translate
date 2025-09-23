# DCS ```.miz``` Translation Tool

这是一个用于游戏```DCS World```的简易翻译工具。

## 使用方法

翻译一个```.miz```文件需要两个文件：

1. 这个```.miz```文件**本身**
2. 这个```.miz```文件的**本地化文件**，为```.csv```格式，与任务文件同名

从哪里获得本地化文件？

1. 从我的仓库中下载，我已将我玩过并校对的战役本地化文件打包上传到了github和gitee中
2. 用本仓库中提供的工具自行翻译

### 1. 已经获得本地化文件

1. 下载本仓库中的```replace.py```和```replace.bat```，把它俩放在任意位置，但需要放在一起

2. 找到你要翻译的战役目录，其路径为```你的安装路径\DCSWorld\Mods\campaigns\战役名称```

   > 以我的Steam版DCS中的“内敌”战役为例，路径为：
   >
   > ```D:\Game\Steam\steamapps\common\DCSWorld\Mods\campaigns\A-10C The Enemy Within 3```

3. 将**本地化文件，即```.csv```文件**，复制到这个目录中

   > 以“内敌”的第一个任务为例，任务文件为```TEW3 M01 FINAL A10C2.miz```
   >
   > 你需要把它的本地化文件，即```TEW3 M01 FINAL A10C2.csv```，和它放在一起，像这样：
   > ```D:\Game\Steam\steamapps\common\DCSWorld\Mods\campaigns\A-10C The Enemy Within 3\TEW3 M01 FINAL A10C2.csv```

4. 把**任务文件，即```.miz```文件**，拖动到```replace.bat```上方，程序会开始替换。你可以选中全部想要翻译的文件，一次性拖动上去

   > 以“内敌”的第一个任务为例，这一步要求你把```TEW3 M01 FINAL A10C2.miz```拖动到```replace.bat```上

5. 程序会自动在任务文件的位置，生成一个```translated```文件夹，翻译后的文件会保存在这个文件夹中

   > 以“内敌”的第一个任务为例，程序会把翻译后的文件放置在这个位置：
   >
   > ```D:\Game\Steam\steamapps\common\DCSWorld\Mods\campaigns\A-10C The Enemy Within 3\translated\TEW3 M01 FINAL A10C2.miz```

6. **备份**全部的原版任务文件，替换为你刚刚得到的翻译版本

### 2. 没有本地化文件

1. 下载本仓库中的```translate.py```和```translate.bat```，把它俩放在任意位置，但需要放在一起

2. 用文本编辑工具，如记事本、VS Code，打开```translate.py```，在```client = OpenAI(api_key="")```中，填写你自己的API

   > 尽管chatgpt是免费的，但调用OpenAI的API并非免费。以保留16句上下文、模型设置为```gpt-5```为参考，翻译一个战役大概0.7-1美元
   >
   > 目前仅支持OpenAI，未来会提供其他AI的支持

3. 找到你要翻译的战役目录，其路径为```你的安装路径\DCSWorld\Mods\campaigns\战役名称```

   > 以我的Steam版DCS中的“内敌”战役为例，路径为：
   >
   > ```D:\Game\Steam\steamapps\common\DCSWorld\Mods\campaigns\A-10C The Enemy Within 3```

4. **任务文件，即```.miz```文件**，拖动到```translate.bat```上方，程序会开始翻译。你可以选中全部想要翻译的文件，一次性拖动上去

   > 以“内敌”的第一个任务为例，这一步要求你把```TEW3 M01 FINAL A10C2.miz```拖动到```translate.bat```上

5. 等待读条结束，程序会输出一个和战役文件同名的```.csv```文件，即为本地化文件

   > 以“内敌”的第一个任务为例，完成翻译后，输出的本地化文件位置为：
   >
   > ```D:\Game\Steam\steamapps\common\DCSWorld\Mods\campaigns\A-10C The Enemy Within 3\TEW3 M01 FINAL A10C2.csv```

6. *如有需要，用excel打开```.csv```文件，人工精修*
7. 现在你已经获得了本地化文件，参考上文，用```replace```程序替换

## Q&A

* 为什么不提供翻译好后的```.miz```？

  因为```DCS World```的更新可能导致AI行为逻辑变化，战役制作者可能需要调整```.miz```。一旦```.miz```被原作者调整，下次```DCS World```更新时，```.miz```会被替换为最新版。而旧版本的```.miz```没经过调整，可能有bug

* 这个程序是什么原理？

  ```.miz```是一个```.zip```压缩包。你可以用解压软件打开看一看。其中的```\l10n\DEFAULT\dictionary```文件是一个文本文件，包含了游戏中出现的全部文字，如无线电菜单选项、无线电字幕、任务提示、任务背景、群组名称、航路点名称等

  ```translation```程序读取了这个文件中需要被翻译的内容，生成了一个```.csv```文件，并调用AI翻译

  ```replace```程序基于```.csv```文件，替换了```.miz```中```\l10n\DEFAULT\dictionary```文件中需要被翻译的字段
