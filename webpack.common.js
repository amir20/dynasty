const ManifestPlugin = require("webpack-manifest-plugin");
const CleanWebpackPlugin = require("clean-webpack-plugin");
const { VueLoaderPlugin } = require("vue-loader");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = {
  context: __dirname + "/assets",
  entry: {
    "clan-page": "./js/clan-page.js",
    "player-page": "./js/player-page.js",
    "troop-page": "./js/troop-page.js",
    index: "./js/index.js",
    common: "./js/common.js",
    styles: "./css/styles.scss"
  },
  optimization: {
    // concatenateModules: true,
    // runtimeChunk: true,
    splitChunks: {
      cacheGroups: {
        commons: {
          test: /node_modules/,
          chunks: "initial",
          name: "vendors"
        },
        "styles-compiled": {
          name: "styles-compiled",
          test: module => module.nameForCondition && /\.(s?css|vue)$/.test(module.nameForCondition()) && !/^javascript/.test(module.type),
          chunks: "all",
          enforce: true
        }
      }
    }
  },
  resolve: {
    extensions: [".js", ".vue", ".json"],
    alias: {
      vue$: "vue/dist/vue.esm.js"
    }
  },
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: ["babel-loader"]
      },
      {
        test: /\.vue$/,
        loader: "vue-loader"
      },
      {
        test: /.*flags.*\.(svg)$/,
        loader: "file-loader",
        options: {
          name: "[name]-[hash].[ext]",
          outputPath: "flags/",
          publicPath: "/static/flags/"
        }
      },
      {
        test: /\.png$/,
        loader: "file-loader",
        options: {
          name: "[name]-[hash].[ext]",
          outputPath: "images/compiled/",
          publicPath: "/static/images/compiled/"
        }
      },
      {
        test: /\.svg$/,
        exclude: [/flags/],
        use: {
          loader: "svg-url-loader"
        }
      },
      {
        test: /\.(sass|scss|css)$/,
        use: [
          MiniCssExtractPlugin.loader,
          {
            loader: "css-loader",
            query: {
              importLoaders: 1
            }
          },
          {
            loader: "postcss-loader",
            options: {
              ident: "postcss",
              plugins: loader => [
                require("postcss-import")(),
                require("postcss-cssnext")({
                  features: {
                    customProperties: { warnings: false }
                  }
                }),
                require("postcss-font-magician")({ display: "swap" })
              ]
            }
          },
          "sass-loader"
        ]
      }
    ]
  },
  plugins: [
    new VueLoaderPlugin(),
    new ManifestPlugin(),
    new CleanWebpackPlugin([
      __dirname + "/clashleaders/static/css",
      __dirname + "/clashleaders/static/js",
      __dirname + "/clashleaders/static/flags",
      __dirname + "/clashleaders/static/images/compiled"
    ])
  ],
  output: {
    path: __dirname + "/clashleaders/static/",
    filename: "js/[name].js",
    publicPath: "/static/"
  }
};
