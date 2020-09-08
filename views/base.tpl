<!DOCTYPE html>
<html lang="en">
  <head>
    <title>{{title}}</title>

    % if defined('description'):
    <meta name="Description" content="{{description}}">
    % end
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <link rel="stylesheet" type="text/css" href="https://necolas.github.io/normalize.css/8.0.1/normalize.css" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&family=Roboto+Slab:wght@500&display=swap" rel="stylesheet" crossorigin>
    <link rel="stylesheet" type="text/css" href="/main.css">

    <meta name="theme-color" content="#0078E7">
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
    <link rel="manifest" href="/site.webmanifest">
  </head>
  <body>
% if get('do_indent', True):
%   from up.misc import indent
{{!indent(base, 4)}}
% else:
{{!base}}
% end

    % if defined('post_scripts'):
    %   for script in post_scripts:
    <script src="/{{script}}.js"></script>
    %   end
    % end
  </body>
</html>
