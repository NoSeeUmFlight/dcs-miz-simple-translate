# DCS ```.miz``` Translation Tool

这是一个用于游戏```DCS World```的简易翻译工具。

## 使用方法

翻译一个```.miz```文件需要两个文件：

1. 这个```.miz```文件**本身**
2. 这个```.miz```文件的**本地化文件**，为```.csv```格式，与任务文件同名

从哪里获得**本地化文件**？

1. 从我的仓库中下载，我已将我玩过并校对的战役本地化文件上传github

   > github仓库地址：
   >
   > https://github.com/NoSeeUmFlight/dcs-campaigns-chinese-localization
   >
   > gitee仓库已不再支持，该仓库因特殊原因已变成私有仓库，无法设置为公开

2. 用本仓库中提供的工具自行翻译

### 1. 已经获得本地化文件

1. 下载本仓库中的```replace.py```和```replace.bat```，把它俩放在相同路径下

   > 比如```replace.py```位于：
   >
   > ```D:\dcs-miz-simple-translate\replace.py```
   >
   > ```replace.bat```位于：
   >
   > ```D:\dcs-miz-simple-translate\replace.bat```

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

6. **备份**原版任务文件，替换为你刚刚得到的翻译版本

### 2. 没有本地化文件

1. 下载本仓库中的```translate.py```和```translate.bat```，把它俩放在相同路径下

   > 比如```translate.py```位于：
   >
   > ```D:\dcs-miz-simple-translate\translate.py```
   >
   > ```translate.bat```位于：
   >
   > ```D:\dcs-miz-simple-translate\translate.bat```

2. 用文本编辑工具，如记事本、VS Code，创建一个```api_key.txt```文档，在其中粘贴OpenAI的API Key并保存，将文件放置在```translate.py```的相同路径下

   > 比如```translate.py```位于：
   >
   > ```D:\dcs-miz-simple-translate\translate.py```
   >
   > 那么，要把```api_key.txt```放在这里：
   >
   > ```D:\dcs-miz-simple-translate\api_key.txt```

   > 目前仅支持OpenAI的API，未来会提供其他AI的支持

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

7. 现在你已经获得了本地化文件，参考上文的**“已经获得本地化文件”**章节，用```replace```程序替换

## Q&A

* 为什么不提供翻译好后的```.miz```？

  因为```DCS World```的更新可能导致AI行为逻辑变化，这可能导致战役出现bug，如僚机不听话或对手不配合剧情演出。一些新功能的引入，如A-10C2的ARC-210电台或FA-18C的DTC卡带，则能增强玩家的游戏体验，而早期版本的战役可能并不支持。因此，战役制作者会时常修复和更新其已经发布的战役。一旦战役被作者调整，下次```DCS World```更新时，```.miz```会被替换为最新版，将失去翻译

  而本地化文件从```.miz```中剥离出了游戏台词和任务提示。只要作者不更改游戏剧情和对话，这些内容不会随更新改变。玩家随时可以把它本地化为中文版

* 这个程序是什么原理？

  ```.miz```是一个```.zip```压缩包，用通常的解压软件就能打开。其中的```\l10n\DEFAULT\dictionary```文件是一个文本文件，包含了游戏中出现的全部文字，如无线电菜单选项、无线电字幕、任务提示、任务背景、群组名称、航路点名称等

  ```translation```程序读取了这个文件中需要被翻译的内容，调用AI翻译，并把字段名、字段编号、原文、译文等内容汇总为一个```.csv```文件

  > 需要注意的是，```\l10n\DEFAULT\dictionary```中的原始文本并不干净。其中包含了一些战役作者调试用的内容，例如“BUTTON 6 OFF”、“INSERT ATTACK  COMPLETE AUDIO”。此外，对话内容并不是按时间顺序排布的，还可能包含一些并未被战役作者实际启用的候选剧情。这导致AI很难从上下文中获知战役剧情，给出符合剧情的翻译
  >
  > 为了尽可能让AI理解上下文，程序会进行启发式搜索。程序会基于字段名、关键字等特征，尝试把相关的语句组合成上下文，供AI理解，但这依旧无法完全取代人工校对的作用
  >
  > 目前，想要获得较高的翻译质量，更稳妥的方法是：由AI给出大致翻译后，玩家在游戏中游玩一遍，了解剧情后再手动校对
  
  ```replace```程序读取```.csv```文件，替换```.miz```中```\l10n\DEFAULT\dictionary```文件中需要被翻译的字段

