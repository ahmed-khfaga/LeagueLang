using System;
using System.Text.RegularExpressions;
using System.Collections.Generic;

class LeagueLangLexer
{
    public static void Main()
    {
        string code = @"
           USE DEMACIA
 SUMMON GAME
 BUILD CHAMPION name = ""Garen""
 BUILD POWER gold = 0
 BUILD POWER target = 1000
 SAY ""Welcome, "" + name + ""!""
 SAY ""Your goal: reach "" + target + "" gold!""
 FARM (gold < target) {
    SAY ""Farming minions...""
    gold = gold + 200
    SAY ""Current gold: "" + gold
 }
 BASE
 SAY ""You reached your target! Time to RECALL.""
 RECALL BASE
        ";

        string[] keywords = {
            "SUMMON", "RECALL", "USE", "BUILD", "SAY", "LISTEN", "ULTIMATE",
            "CALL", "CHECK", "MISS", "FARM", "BASE", "FF15"
        };

        string keywordPattern = @"\b(" + string.Join("|", keywords) + @")\b";
        var tokenPatterns = new Dictionary<string, string>
        {
            { "COMMENT", @"//.*" },
            { "STRING", "\".*?\"" },
            { "NUMBER", @"\b\d+(\.\d+)?\b" },
            { "KEYWORD", keywordPattern },
            { "IDENTIFIER", @"\b[A-Za-z_]\w*\b" },
            { "SYMBOL", @"[{}();]" },
            { "OPERATOR", @"[+\-*/=<>!]" }
        };

        foreach (var token in Tokenize(code, tokenPatterns))
        {
            Console.WriteLine($"[{token.Type}]  {token.Value}");
        }
    }

    record Token(string Type, string Value);

    static IEnumerable<Token> Tokenize(string code, Dictionary<string, string> patterns)
    {
        string fullPattern = string.Join("|", patterns.Select(p => $"(?<{p.Key}>{p.Value})"));
        Regex regex = new Regex(fullPattern);

        foreach (Match match in regex.Matches(code))
        {
            foreach (var key in patterns.Keys)
            {
                if (match.Groups[key].Success)
                {
                    yield return new Token(key, match.Groups[key].Value);
                    break;
                }
            }
        }
    }
}
