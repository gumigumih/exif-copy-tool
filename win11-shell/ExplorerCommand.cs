using System.Buffers;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text.Json;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.System.Com;
using Windows.Win32.UI.Shell;

namespace ExifCopyTool.Win11Shell;

internal static class ShellConstants
{
    public const string AppName = "ExifCopyTool";
    public const string AppExeName = "ExifCopyTool.exe";
    public const string FormatsFileName = "formats.json";
    public const string IconFileName = "ExifCopyTool.ico";
    public static readonly Guid ExplorerCommandClsid = new("537C902B-D7F5-4F92-8C58-BC9EC5957F13");
}

[ComVisible(true)]
[ClassInterface(ClassInterfaceType.None)]
[Guid("537C902B-D7F5-4F92-8C58-BC9EC5957F13")]
public sealed class ExplorerCommand : IExplorerCommand
{
    private readonly bool _isLeaf;
    private readonly CommandDefinition _definition;
    private readonly IReadOnlyList<CommandDefinition>? _subcommands;

    public ExplorerCommand()
    {
        _definition = default;
        _subcommands = LoadFormats();
    }

    private ExplorerCommand(CommandDefinition definition)
    {
        _definition = definition;
        _isLeaf = true;
    }

    private ExplorerCommand(IReadOnlyList<CommandDefinition> subcommands)
    {
        _subcommands = subcommands;
    }

    private bool IsLeaf => _isLeaf;

    private static ExplorerCommand CreateLeaf(CommandDefinition definition) => new(definition);

    unsafe void IExplorerCommand.GetTitle(IShellItemArray psiItemArray, PWSTR* ppszName)
    {
        WriteString(ppszName, IsLeaf ? _definition.Name : "EXIF情報をコピー");
    }

    unsafe void IExplorerCommand.GetIcon(IShellItemArray psiItemArray, PWSTR* ppszIcon)
    {
        WriteString(ppszIcon, GetIconResourceString());
    }

    unsafe void IExplorerCommand.GetToolTip(IShellItemArray psiItemArray, PWSTR* ppszInfotip)
    {
        WriteString(ppszInfotip, IsLeaf ? $"{_definition.Name} でEXIF情報をコピーします。" : "フォーマットを選んでEXIF情報をコピーします。");
    }

    unsafe void IExplorerCommand.GetCanonicalName(Guid* pguidCommandName)
    {
        if (pguidCommandName is null)
        {
            return;
        }

        *pguidCommandName = IsLeaf
            ? StableGuid($"ExifCopyTool.Win11Shell:{_definition.Name}")
            : ShellConstants.ExplorerCommandClsid;
    }

    void IExplorerCommand.GetState(IShellItemArray psiItemArray, BOOL fOkToBeSlow, out _EXPCMDSTATE pCmdState)
    {
        pCmdState = _EXPCMDSTATE.ECS_ENABLED;
    }

    void IExplorerCommand.Invoke(IShellItemArray psiItemArray, IBindCtx pbc)
    {
        try
        {
            if (IsLeaf)
            {
                InvokeCopy(_definition.Name, GetSelectionPaths(psiItemArray));
                return;
            }

            if (_subcommands is { Count: > 0 })
            {
                var defaultCommand = CreateLeaf(_subcommands[0]);
                ((IExplorerCommand)defaultCommand).Invoke(psiItemArray, pbc);
            }
        }
        catch
        {
            // Explorer context menu callbacks should fail quietly.
        }
    }

    void IExplorerCommand.GetFlags(out _EXPCMDFLAGS pFlags)
    {
        pFlags = IsLeaf ? _EXPCMDFLAGS.ECF_DEFAULT : _EXPCMDFLAGS.ECF_HASSUBCOMMANDS;
    }

    void IExplorerCommand.EnumSubCommands(out IEnumExplorerCommand ppEnum)
    {
        if (IsLeaf || _subcommands is not { Count: > 0 })
        {
            ppEnum = new ExplorerCommandEnumerator(Array.Empty<ExplorerCommand>());
            return;
        }

        var children = new ExplorerCommand[_subcommands.Count];
        for (var i = 0; i < _subcommands.Count; i++)
        {
            children[i] = CreateLeaf(_subcommands[i]);
        }

        ppEnum = new ExplorerCommandEnumerator(children);
    }

    private static string GetIconResourceString()
    {
        var iconPath = Path.Combine(AppContext.BaseDirectory, ShellConstants.IconFileName);
        if (!File.Exists(iconPath))
        {
            iconPath = Path.Combine(AppContext.BaseDirectory, ShellConstants.AppExeName);
        }

        return $"{iconPath},0";
    }

    private static unsafe void WriteString(PWSTR* target, string value)
    {
        if (target is null)
        {
            return;
        }

        var ptr = Marshal.StringToCoTaskMemUni(value ?? string.Empty);
        *target = new PWSTR((char*)ptr);
    }

    private static IReadOnlyList<CommandDefinition> LoadFormats()
    {
        var formatsPath = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            ShellConstants.AppName,
            ShellConstants.FormatsFileName);

        try
        {
            if (File.Exists(formatsPath))
            {
                var json = File.ReadAllText(formatsPath);
                var parsed = JsonSerializer.Deserialize<List<FormatRecord>>(json, JsonOptions.Default);
                var formats = parsed?
                    .Where(x => !string.IsNullOrWhiteSpace(x.Name))
                    .Select(x => new CommandDefinition(x.Name!.Trim(), x.Template ?? string.Empty))
                    .ToList();

                if (formats is { Count: > 0 })
                {
                    return formats;
                }
            }
        }
        catch
        {
            // Fall back to the embedded defaults.
        }

        return DefaultFormats;
    }

    private static IReadOnlyList<string> GetSelectionPaths(IShellItemArray items)
    {
        var paths = new List<string>();
        try
        {
            items.GetCount(out uint count);
            for (uint i = 0; i < count; i++)
            {
                try
                {
                    items.GetItemAt(i, out IShellItem item);
                    var path = TryGetFileSystemPath(item);
                    if (!string.IsNullOrWhiteSpace(path))
                    {
                        paths.Add(path);
                    }
                }
                catch
                {
                    // Ignore individual item failures.
                }
            }
        }
        catch
        {
        }

        return paths;
    }

    private static unsafe string? TryGetFileSystemPath(IShellItem item)
    {
        PWSTR value = default;
        try
        {
            item.GetDisplayName(SIGDN.SIGDN_FILESYSPATH, &value);
            return value.Value is null ? null : value.ToString();
        }
        catch
        {
            return null;
        }
        finally
        {
            if (value.Value is not null)
            {
                PInvoke.CoTaskMemFree(value.Value);
            }
        }
    }

    private static void InvokeCopy(string formatName, IReadOnlyList<string> paths)
    {
        if (paths.Count == 0)
        {
            return;
        }

        var exePath = Path.Combine(AppContext.BaseDirectory, ShellConstants.AppExeName);
        if (!File.Exists(exePath))
        {
            return;
        }

        var startInfo = new ProcessStartInfo(exePath)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = AppContext.BaseDirectory,
        };

        startInfo.ArgumentList.Add("--copy");
        startInfo.ArgumentList.Add(formatName);
        foreach (var path in paths)
        {
            startInfo.ArgumentList.Add(path);
        }

        Process.Start(startInfo);
    }

    private static Guid StableGuid(string value)
    {
        var hash = SHA1.HashData(System.Text.Encoding.UTF8.GetBytes(value));
        Span<byte> bytes = stackalloc byte[16];
        hash.AsSpan(0, 16).CopyTo(bytes);
        bytes[6] = (byte)((bytes[6] & 0x0F) | 0x50);
        bytes[8] = (byte)((bytes[8] & 0x3F) | 0x80);
        return new Guid(bytes);
    }

    private static readonly IReadOnlyList<CommandDefinition> DefaultFormats =
    [
        new CommandDefinition("撮影設定", "{Make} {Model}\n{LensModel}\n{FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n{DateTimeOriginal}"),
        new CommandDefinition("SNS用", "📷 {Make} {Model}\n🔭 {LensModel}\n⚙️ {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}"),
        new CommandDefinition("Markdown", "**Camera:** {Make} {Model}\n**Lens:** {LensModel}\n**Settings:** {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n**Date:** {DateTimeOriginal}"),
        new CommandDefinition("全部ざっくり", "File: {FileName}\nDate: {DateTimeOriginal}\nCamera: {Make} {Model}\nLens: {LensModel}\nSettings: {FocalLength} / F{FNumber} / {ExposureTime} / ISO{ISO}\n35mm: {FocalLengthIn35mmFormat}"),
    ];

    private sealed record FormatRecord(string? Name, string? Template);
}

[ComVisible(true)]
[ClassInterface(ClassInterfaceType.None)]
public sealed class ExplorerCommandEnumerator : IEnumExplorerCommand
{
    private readonly IReadOnlyList<ExplorerCommand> _commands;
    private int _index;

    public ExplorerCommandEnumerator(IReadOnlyList<ExplorerCommand> commands, int startIndex = 0)
    {
        _commands = commands;
        _index = Math.Clamp(startIndex, 0, commands.Count);
    }

    unsafe HRESULT IEnumExplorerCommand.Next(uint celt, IExplorerCommand[] pUICommand, uint* pceltFetched)
    {
        if (pceltFetched is not null)
        {
            *pceltFetched = 0;
        }

        if (pUICommand is null || pUICommand.Length < celt)
        {
            return (HRESULT)unchecked((int)0x80004003);
        }

        uint fetched = 0;
        while (fetched < celt && _index < _commands.Count)
        {
            pUICommand[fetched] = _commands[_index];
            fetched++;
            _index++;
        }

        if (pceltFetched is not null)
        {
            *pceltFetched = fetched;
        }

        return fetched == celt ? (HRESULT)0 : (HRESULT)1;
    }

    void IEnumExplorerCommand.Skip(uint celt)
    {
        _index = (int)Math.Min((uint)_commands.Count, (uint)(_index + celt));
    }

    void IEnumExplorerCommand.Reset()
    {
        _index = 0;
    }

    void IEnumExplorerCommand.Clone(out IEnumExplorerCommand ppenum)
    {
        ppenum = new ExplorerCommandEnumerator(_commands, _index);
    }
}

internal readonly record struct CommandDefinition(string Name, string Template);

internal static class JsonOptions
{
    public static readonly JsonSerializerOptions Default = new()
    {
        PropertyNameCaseInsensitive = true,
    };
}
